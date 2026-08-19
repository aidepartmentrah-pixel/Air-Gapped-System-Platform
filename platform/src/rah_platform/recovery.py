"""Recovery — PL8b (second of two tracked `PL8` sub-slices; see
`backup.py`'s own module docstring for the `PL8a`/`PL8b` split
rationale).

Implements §7.24 (Recovery History Rule) and §9.22's own recovery-facing
half: after a real `INSTALL`/`UPDATE` failure, restore *host* state back
to match what the Registry already, correctly, still claims is active —
recovery in Period A never changes *which* Release is active, it repairs
the host to agree with the Registry, which §9.22 already guarantees was
never falsely overwritten by the failed operation itself. This keeps the
implementation genuinely simple: no Registry commit logic is needed here
at all, only a real restore script + real re-verification.

**Recovery always creates its own, separate operation record** (§7.24:
"It shall not collapse these into one rewritten deployment record. The
history must show both the failure and the attempted correction.") —
`recover_application` never reuses `failed_operation_id`; it only
references it in `details`/event data.

**`RESTORE_PREVIOUS_STATE` is the only implemented `recovery_mode`** in
Period A — an honest `RecoveryUnsupportedError` for anything else,
matching this Platform's standing "never fabricate support for a
capability nothing actually checks" discipline.
"""

from __future__ import annotations

import os
import threading

from rah_platform import application_query, operations, verification
from rah_platform.application_query import get_application_row, get_release_row
from rah_platform.config import Config
from rah_platform.errors import (
    ApplicationNotInstalledError,
    BackupBelongsToAnotherApplicationError,
    BackupNotFoundError,
    InternalError,
    PlatformError,
    PreviousOperationalStateUnavailableError,
    RecoveryPrerequisitesFailedError,
    RecoveryUnsupportedError,
    RecoveryVerificationFailedError,
    RestoreScriptFailedError,
    ScriptTimedOutError,
)
from rah_platform.installation import run_script
from rah_platform.models import backups, deployment_configuration, deployments, release_storage

_SUPPORTED_RECOVERY_MODES = {"RESTORE_PREVIOUS_STATE"}


def _resolve_backup(conn, backup_id: str, application_id: str):
    row = conn.execute(backups.select().where(backups.c.backup_id == backup_id)).mappings().first()
    if row is None:
        raise BackupNotFoundError("No backup exists with the given backup_id.", details={"backup_id": backup_id})
    if row["application_id"] != application_id:
        raise BackupBelongsToAnotherApplicationError(
            "The selected backup does not belong to this application.",
            details={"application_id": application_id, "backup_id": backup_id},
        )
    return row


def _release_storage_directory(conn, release_id: str) -> str:
    row = conn.execute(release_storage.select().where(release_storage.c.release_id == release_id)).mappings().first()
    return row["directory_name"]


def _perform_restore(engine, config: Config, *, operation_id: str, application_id: str, backup_row) -> dict:
    """Restores `backup_row`'s artifact into the *currently active*
    deployment (not necessarily the deployment the backup was originally
    taken from) — the active release's own restore script is what knows
    how to consume that backup format back into a running deployment,
    and restoring "in place" is what makes §9.22's "never change which
    Release is active" guarantee trivially true here: this function never
    touches `applications.active_deployment_id`.
    """
    with engine.connect() as conn:
        application_row = get_application_row(conn, application_id)
        active_deployment_id = application_row["active_deployment_id"]
        if not active_deployment_id:
            raise PreviousOperationalStateUnavailableError(
                "There is no active deployment to restore into.", details={"application_id": application_id}
            )
        deployment_row = conn.execute(
            deployments.select().where(deployments.c.deployment_id == active_deployment_id)
        ).mappings().first()
        release_row = get_release_row(conn, deployment_row["release_id"])

    manifest = release_row["manifest"]
    slug = manifest["application"]["slug"]
    canonical_path = os.path.join(config.deployments_path, slug)

    entrypoint = manifest["deployment"]["entrypoints"].get("restore") or manifest.get("database", {}).get("recovery", {}).get("entrypoint")
    if not entrypoint:
        raise RecoveryUnsupportedError(
            "This Release declares no restore entrypoint.", details={"release_id": release_row["release_id"]}
        )

    with engine.connect() as conn:
        directory_name = _release_storage_directory(conn, release_row["release_id"])
    script_path = os.path.join(config.release_storage_path, directory_name, "scripts", entrypoint)
    if not os.path.isfile(script_path):
        raise RestoreScriptFailedError(
            "The declared restore script does not exist.",
            stage="RESTORING",
            details={"entrypoint": entrypoint},
        )

    exit_code, stdout, stderr = run_script(
        script_path,
        timeout_seconds=config.install_script_timeout_seconds,
        extra_env={
            "RAH_BACKUP_SOURCE_PATH": backup_row["storage_path"],
            "RAH_ACTIVE_DEPLOYMENT_PATH": canonical_path,
        },
    )
    with engine.begin() as conn:
        operations.log(
            conn,
            operation_id,
            f"Restore script exited with code {exit_code}." if exit_code is not None else "Restore script timed out.",
            details={"exit_code": exit_code, "stderr_tail": (stderr or "")[-2000:]},
        )
    if exit_code is None:
        raise ScriptTimedOutError(
            "The restore script did not complete within the configured timeout.",
            stage="RESTORING",
            details={"timeout_seconds": config.install_script_timeout_seconds},
        )
    if exit_code != 0:
        raise RestoreScriptFailedError(
            "The restore script failed.",
            stage="RESTORING",
            details={"exit_code": exit_code, "stderr_tail": (stderr or "")[-2000:]},
        )

    with engine.begin() as conn:
        conn.execute(backups.update().where(backups.c.backup_id == backup_row["backup_id"]).values(status="RESTORED"))
        operations.append_event(
            conn, operation_id, "RESTORE_COMPLETED", status="PASS", message="Backup restored.",
            details={"backup_id": backup_row["backup_id"]},
        )

    with engine.connect() as conn:
        configuration_rows = conn.execute(
            deployment_configuration.select().where(
                deployment_configuration.c.deployment_id == deployment_row["deployment_id"],
                deployment_configuration.c.secret.is_(False),
            )
        ).mappings().all()
    configuration_values = {r["key"]: r["value"] for r in configuration_rows}

    verification_result = verification.run_verification(
        engine,
        application_id=application_id,
        expected_release_id=release_row["release_id"],
        verification_type="RECOVERY",
        operation_id=operation_id,
        configuration_values=configuration_values,
    )
    with engine.begin() as conn:
        operations.append_event(
            conn, operation_id, "VERIFICATION_COMPLETED", status=verification_result["status"], message="Post-recovery verification.",
            details={"verification_run_id": verification_result["verification_run_id"], "summary": verification_result["summary"]},
        )
    if verification_result["status"] != "PASS":
        raise RecoveryVerificationFailedError(
            "One or more mandatory post-recovery verification checks failed.",
            stage="VERIFYING",
            details={"verification_run_id": verification_result["verification_run_id"], "summary": verification_result["summary"]},
        )

    return {"release_row": release_row, "verification_result": verification_result}


# --- Standalone Restore Backup (§6.35) ---


def _execute_restore(engine, config: Config, operation_id: str, application_id: str, backup_row) -> None:
    try:
        _perform_restore(engine, config, operation_id=operation_id, application_id=application_id, backup_row=backup_row)
        operations.succeed_operation(engine, operation_id)
    except Exception as exc:
        error = exc if isinstance(exc, PlatformError) else InternalError(
            "Restore failed unexpectedly.", details={"reason": str(exc)}
        )
        operations.fail_operation(engine, operation_id, error)


def restore_backup(engine, config: Config, *, application_id: str, backup_id: str, requested_by: str, reason: str | None = None) -> dict:
    """The standalone, API-facing entry point (`POST
    .../backups/{id}/restore`, §6.35). §6.35: `202 Accepted` with an
    operation reference — restoring a real backup runs a real script.
    """
    with engine.connect() as conn:
        application_row = get_application_row(conn, application_id)
        if not application_row["active_deployment_id"]:
            raise ApplicationNotInstalledError(
                "The application is not installed; there is nothing to restore into.",
                details={"application_id": application_id},
            )
        backup_row = _resolve_backup(conn, backup_id, application_id)

    operation = operations.create_operation(
        engine, operation_type="RESTORE", application_id=application_id, requested_by=requested_by
    )
    operation_id = operation["operation_id"]
    operations.start_operation(engine, operation_id)

    thread = threading.Thread(
        target=_execute_restore, args=(engine, config, operation_id, application_id, backup_row), daemon=True
    )
    thread.start()

    return operations.get_operation(engine, operation_id)


# --- Recover Application (§6.36, §7.24) ---


def _execute_recovery(engine, config: Config, operation_id: str, application_id: str, failed_operation_id: str | None, backup_id: str, recovery_mode: str) -> None:
    try:
        with engine.connect() as conn:
            backup_row = _resolve_backup(conn, backup_id, application_id)
        result = _perform_restore(engine, config, operation_id=operation_id, application_id=application_id, backup_row=backup_row)
        with engine.begin() as conn:
            operations.append_event(
                conn, operation_id, "RECOVERY_COMPLETED", status="PASS", message="Recovery completed.",
                details={
                    "failed_operation_id": failed_operation_id,
                    "backup_id": backup_id,
                    "recovery_mode": recovery_mode,
                    "resulting_active_release_id": result["release_row"]["release_id"],
                },
            )
        operations.succeed_operation(engine, operation_id)
    except Exception as exc:
        error = exc if isinstance(exc, PlatformError) else InternalError(
            "Recovery failed unexpectedly.", details={"reason": str(exc)}
        )
        operations.fail_operation(engine, operation_id, error)


def recover_application(
    engine, config: Config, *, application_id: str, failed_operation_id: str | None = None, backup_id: str,
    recovery_mode: str = "RESTORE_PREVIOUS_STATE", requested_by: str, reason: str | None = None,
) -> dict:
    """The broader, application-facing entry point (`POST
    .../applications/{id}/recover`, §6.36) — validates the recovery
    context (`RECOVER` actually allowed per `application_query
    .get_available_actions`) before delegating to the same real restore
    implementation `restore_backup` uses.

    `failed_operation_id` is optional — real `PL9b` offline acceptance
    testing found that requiring one made drift-triggered recovery
    (host drift detected with no failed operation behind it, e.g. a
    manually stopped container) permanently unreachable, even though
    `get_available_actions` now correctly allows `RECOVER` for that case
    too (see `application_query._evaluate_recover`). When supplied, it
    is still validated for real; when omitted, the broader
    `RECOVER`-availability check below is the only gate.
    """
    if recovery_mode not in _SUPPORTED_RECOVERY_MODES:
        raise RecoveryUnsupportedError(
            "Only RESTORE_PREVIOUS_STATE is implemented in Period A.",
            details={"recovery_mode": recovery_mode, "supported": sorted(_SUPPORTED_RECOVERY_MODES)},
        )

    if failed_operation_id is not None:
        failed_operation = operations.get_operation(engine, failed_operation_id)
        if failed_operation["application_id"] != application_id or failed_operation["status"] != "FAILED":
            raise RecoveryPrerequisitesFailedError(
                "The referenced operation is not a failed operation for this application.",
                details={"failed_operation_id": failed_operation_id},
            )

    actions = application_query.get_available_actions(engine, application_id)
    recover_action = next(a for a in actions["actions"] if a["action"] == "RECOVER")
    if not recover_action["allowed"]:
        raise RecoveryPrerequisitesFailedError(
            "Recovery cannot proceed.",
            details={"blocking_reasons": recover_action["blocking_reasons"]},
        )

    with engine.connect() as conn:
        _resolve_backup(conn, backup_id, application_id)  # real ownership check before creating the operation

    operation = operations.create_operation(
        engine, operation_type="RECOVER", application_id=application_id, requested_by=requested_by
    )
    operation_id = operation["operation_id"]
    operations.start_operation(engine, operation_id)

    thread = threading.Thread(
        target=_execute_recovery,
        args=(engine, config, operation_id, application_id, failed_operation_id, backup_id, recovery_mode),
        daemon=True,
    )
    thread.start()

    return operations.get_operation(engine, operation_id)
