"""Backup — PL8a (first half of Backup + Update, per the pre-PL0 review's
`PL8a`/`PL8b` split — see `docs/development/Period A — Independent
Product Development; Platform/2. Initial Slicing Task Table.md`, "One
slice too large: PL8").

Implements §7.22 (Backup Requirement Rule), §7.23 (Backup Ownership
Rule), §9.19 (Backup-Before-Update Rule), and §9.20 (Backup Isolation
Rule). Only `backup_type: DATABASE` is real in Period A — `FILES`/
`FULL_DEPLOYMENT` are declared by the Contract's schema but no Golden
Fixture or manifest field models them yet, so `create_backup` honestly
rejects them (`BackupUnsupportedError`) rather than fabricating a no-op
success.

**What "backup" actually does here**: runs the target Release's own
declared `database.backup_before_update.entrypoint` script — a real
subprocess, same execution primitive as `installation.run_script` — with
`RAH_ACTIVE_DEPLOYMENT_PATH` (the currently-live deployment, whatever it
holds) and `RAH_BACKUP_OUTPUT_PATH` (a Platform-computed destination
under `config.backups_path/<slug>/<timestamp>/`, per §9.20's isolation
requirement: outside the Release Package, outside the deployment
directory) passed as real environment variables. The script's only job
is to produce a real file at that path; the Platform then computes a
real SHA-256 over it — never a fabricated checksum.

**Which release's manifest declares the backup script**: the *target*
release being updated to, not the currently-active one — matching `PL5`'s
`prepare_update`, which already reads `database.backup_before_update`
from `target_release_row`. A Decision, not an architecture-mandated
choice (the architecture text doesn't disambiguate); documented in the
Slicing Task Table.

**Operation identity**: a backup taken as the mandatory pre-update step
shares the parent UPDATE operation's `operation_id` (architecture "Choose
Implementation Mechanisms" doc §7.5.5, "Shared Operation for Sub-Steps")
— `perform_backup` takes `operation_id` as a plain parameter so
`update.py` can pass its own. A standalone `POST .../backups` call
creates its own dedicated `BACKUP` operation via `create_backup`.
"""

from __future__ import annotations

import hashlib
import os
import threading
import uuid
from datetime import datetime, timezone

from rah_platform import operations
from rah_platform.application_query import get_application_row, get_release_row
from rah_platform.config import Config
from rah_platform.errors import (
    ApplicationNotInstalledError,
    BackupArtifactMissingError,
    BackupCreationFailedError,
    BackupNotFoundError,
    BackupScriptMissingError,
    BackupUnsupportedError,
    InternalError,
    PlatformError,
    ScriptTimedOutError,
)
from rah_platform.installation import run_script
from rah_platform.models import backups, deployments, release_storage

_SUPPORTED_BACKUP_TYPES = {"DATABASE"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _release_storage_directory(conn, release_id: str) -> str:
    row = conn.execute(release_storage.select().where(release_storage.c.release_id == release_id)).mappings().first()
    return row["directory_name"]


def perform_backup(
    engine,
    config: Config,
    *,
    operation_id: str,
    application_id: str,
    deployment_id: str | None,
    release_row,
    backup_type: str,
    verify_after_creation: bool,
    active_canonical_path: str,
) -> dict:
    """The real, reusable backup step — called directly (synchronously)
    by both `create_backup`'s own background thread and `update.py`'s
    `_execute_update` (as the `BACKING_UP` stage of the same operation).
    """
    manifest = release_row["manifest"]

    if backup_type not in _SUPPORTED_BACKUP_TYPES:
        raise BackupUnsupportedError(
            "This Platform only implements DATABASE backups in Period A.",
            details={"backup_type": backup_type, "supported": sorted(_SUPPORTED_BACKUP_TYPES)},
        )

    backup_decl = manifest.get("database", {}).get("backup_before_update", {})
    entrypoint = backup_decl.get("entrypoint")
    if not entrypoint:
        raise BackupUnsupportedError(
            "This Release does not declare a backup entrypoint.",
            details={"release_id": release_row["release_id"]},
        )

    with engine.connect() as conn:
        directory_name = _release_storage_directory(conn, release_row["release_id"])
    script_path = os.path.join(config.release_storage_path, directory_name, "scripts", entrypoint)
    if not os.path.isfile(script_path):
        raise BackupScriptMissingError(
            "The declared backup script does not exist.",
            details={"entrypoint": entrypoint},
        )

    slug = manifest["application"]["slug"]
    timestamp = _now().strftime("%Y%m%dT%H%M%S%f")
    storage_path = os.path.join(config.backups_path, slug, timestamp, "database.dump")

    exit_code, stdout, stderr = run_script(
        script_path,
        timeout_seconds=config.install_script_timeout_seconds,
        extra_env={
            "RAH_ACTIVE_DEPLOYMENT_PATH": active_canonical_path,
            "RAH_BACKUP_OUTPUT_PATH": storage_path,
        },
    )
    with engine.begin() as conn:
        operations.log(
            conn,
            operation_id,
            f"Backup script exited with code {exit_code}." if exit_code is not None else "Backup script timed out.",
            details={"exit_code": exit_code, "stderr_tail": (stderr or "")[-2000:]},
        )

    if exit_code is None:
        raise ScriptTimedOutError(
            "The backup script did not complete within the configured timeout.",
            stage="BACKING_UP",
            details={"timeout_seconds": config.install_script_timeout_seconds},
        )
    if exit_code != 0:
        raise BackupCreationFailedError(
            "The backup script failed.",
            stage="BACKING_UP",
            details={"exit_code": exit_code, "stderr_tail": (stderr or "")[-2000:]},
        )
    if not os.path.isfile(storage_path):
        raise BackupArtifactMissingError(
            "The backup script exited successfully but produced no artifact.",
            stage="BACKING_UP",
            details={"storage_path": storage_path},
        )

    checksum = hashlib.sha256(open(storage_path, "rb").read()).hexdigest()
    status = "VERIFIED" if verify_after_creation else "CREATED"
    verified = bool(verify_after_creation)
    verified_at = _now() if verify_after_creation else None
    backup_id = str(uuid.uuid4())
    created_at = _now()

    with engine.begin() as conn:
        conn.execute(
            backups.insert().values(
                backup_id=backup_id,
                operation_id=operation_id,
                application_id=application_id,
                deployment_id=deployment_id,
                backup_type=backup_type,
                storage_path=storage_path,
                checksum=checksum,
                status=status,
                verified=verified,
                verified_at=verified_at,
                created_at=created_at,
                notes=None,
            )
        )
        operations.append_event(
            conn,
            operation_id,
            "BACKUP_COMPLETED",
            status="PASS",
            message="Backup created.",
            details={"backup_id": backup_id, "storage_path": storage_path, "checksum": checksum},
        )

    return _backup_result(
        backup_id=backup_id,
        operation_id=operation_id,
        application_id=application_id,
        deployment_id=deployment_id,
        backup_type=backup_type,
        storage_path=storage_path,
        checksum=checksum,
        status=status,
        verified=verified,
        verified_at=verified_at,
        created_at=created_at,
        notes=None,
    )


def _backup_result(**row) -> dict:
    return {
        "backup_id": row["backup_id"],
        "operation_id": row["operation_id"],
        "application_id": row["application_id"],
        "deployment_id": row["deployment_id"],
        "backup_type": row["backup_type"],
        "storage_path": row["storage_path"],
        "checksum": row["checksum"],
        "status": row["status"],
        "verified": row["verified"],
        "verified_at": row["verified_at"].isoformat() if row["verified_at"] else None,
        "created_at": row["created_at"].isoformat(),
        "notes": row["notes"],
    }


def _execute_standalone_backup(
    engine, config: Config, operation_id: str, application_id: str, deployment_id: str, release_row, backup_type: str, verify_after_creation: bool, active_canonical_path: str
) -> None:
    try:
        perform_backup(
            engine,
            config,
            operation_id=operation_id,
            application_id=application_id,
            deployment_id=deployment_id,
            release_row=release_row,
            backup_type=backup_type,
            verify_after_creation=verify_after_creation,
            active_canonical_path=active_canonical_path,
        )
        operations.succeed_operation(engine, operation_id)
    except Exception as exc:
        error = exc if isinstance(exc, PlatformError) else InternalError(
            "Backup failed unexpectedly.", details={"reason": str(exc)}
        )
        operations.fail_operation(engine, operation_id, error)


def create_backup(
    engine, config: Config, *, application_id: str, backup_type: str, verify_after_creation: bool, requested_by: str, reason: str | None = None
) -> dict:
    """The standalone, API-facing entry point (`POST
    .../applications/{id}/backups`). §6.31: `202 Accepted` with an
    operation reference — a real script may genuinely take a while, same
    async justification as `PL6`'s install.
    """
    with engine.connect() as conn:
        application_row = get_application_row(conn, application_id)
        active_deployment_id = application_row["active_deployment_id"]
        if not active_deployment_id:
            raise ApplicationNotInstalledError(
                "The application is not installed; there is nothing to back up.",
                details={"application_id": application_id},
            )
        deployment_row = conn.execute(
            deployments.select().where(deployments.c.deployment_id == active_deployment_id)
        ).mappings().first()
        release_row = get_release_row(conn, deployment_row["release_id"])

    slug = release_row["manifest"]["application"]["slug"]
    active_canonical_path = os.path.join(config.deployments_path, slug)

    operation = operations.create_operation(
        engine, operation_type="BACKUP", application_id=application_id, requested_by=requested_by
    )
    operation_id = operation["operation_id"]
    operations.start_operation(engine, operation_id)

    thread = threading.Thread(
        target=_execute_standalone_backup,
        args=(engine, config, operation_id, application_id, active_deployment_id, release_row, backup_type, verify_after_creation, active_canonical_path),
        daemon=True,
    )
    thread.start()

    return operations.get_operation(engine, operation_id)


def list_backups(engine, application_id: str) -> dict:
    with engine.connect() as conn:
        get_application_row(conn, application_id)
        rows = conn.execute(
            backups.select().where(backups.c.application_id == application_id).order_by(backups.c.created_at.desc())
        ).mappings().all()
    return {"items": [_backup_result(**row) for row in rows]}


def get_backup(engine, backup_id: str) -> dict:
    with engine.connect() as conn:
        row = conn.execute(backups.select().where(backups.c.backup_id == backup_id)).mappings().first()
    if row is None:
        raise BackupNotFoundError(
            "No backup exists with the given backup_id.", details={"backup_id": backup_id}
        )
    return _backup_result(**row)
