"""Application State and Action Intelligence — PL4.

Answers, from Registry state alone: what applications exist, what
Releases belong to them, what's currently active, and which of
`INSTALL`/`UPDATE`/`DOWNGRADE`/`REINSTALL`/`VERIFY`/`BACKUP`/`RECOVER`
the operator may currently request (§2.3, §7.20/§7.21 Transition/
Downgrade Rules). No lifecycle script runs here — this is read-only
reasoning over what's already imported and (if anything) already
installed.

No real installation exists until `PL6`, so `active_deployment`/
`deployments` rows never come from a real install in this slice's own
tests — they're seeded directly to exercise the already-installed
decision paths, exactly as the pre-PL0 review anticipated for this slice.

`operational_health` is reported as `UNKNOWN` for any installed
application, never `HEALTHY` — the Platform has no real host verification
evidence until `PL7`, and §5.24's Result Authority Principle is explicit
that a result "shall not claim more than the evidence supports."
"""

from __future__ import annotations

import sqlalchemy as sa

from rah_platform.errors import (
    ApplicationNotFoundError,
    ReleaseBelongsToAnotherApplicationError,
    ReleaseNotFoundError,
)
from rah_platform.models import applications, deployments, releases, release_storage


def _get_application_row(conn, application_id: str):
    row = conn.execute(
        applications.select().where(applications.c.application_id == application_id)
    ).mappings().first()
    if row is None:
        raise ApplicationNotFoundError(
            "No application exists with the given application_id.",
            details={"application_id": application_id},
        )
    return row


def _get_release_row(conn, release_id: str):
    row = conn.execute(releases.select().where(releases.c.release_id == release_id)).mappings().first()
    if row is None:
        raise ReleaseNotFoundError(
            "No release exists with the given release_id.", details={"release_id": release_id}
        )
    return row


def _get_active_deployment_row(conn, application_row):
    if not application_row["active_deployment_id"]:
        return None
    return conn.execute(
        deployments.select().where(deployments.c.deployment_id == application_row["active_deployment_id"])
    ).mappings().first()


def _storage_state(conn, release_row) -> str:
    storage = conn.execute(
        release_storage.select().where(release_storage.c.release_id == release_row["release_id"])
    ).mappings().first()
    return storage["state"] if storage else "REMOVED_FROM_STORAGE"


def _release_deployment_state(conn, release_row, active_deployment_row) -> str:
    if _storage_state(conn, release_row) == "REMOVED_FROM_STORAGE":
        return "REMOVED_FROM_STORAGE"
    if active_deployment_row and active_deployment_row["release_id"] == release_row["release_id"]:
        return "ACTIVE"
    ever_deployed = conn.execute(
        sa.select(sa.func.count()).select_from(deployments).where(deployments.c.release_id == release_row["release_id"])
    ).scalar()
    return "PREVIOUSLY_DEPLOYED" if ever_deployed else "NEVER_DEPLOYED"


def _release_result(conn, release_row, active_deployment_row) -> dict:
    manifest = release_row["manifest"]
    supported = manifest["deployment"]["supported_operations"]
    return {
        "id": release_row["release_id"],
        "application_id": release_row["application_id"],
        "version": release_row["version"],
        "summary": release_row["summary"],
        "created_at_engineering": release_row["created_at_engineering"],
        "imported_at": release_row["imported_at"].isoformat(),
        "contract_version": release_row["contract_version"],
        "manifest_schema_version": release_row["manifest_schema_version"],
        "storage_state": _storage_state(conn, release_row),
        "release_fingerprint": release_row["fingerprint"],
        "supported_operations": {
            "fresh_install": bool(supported.get("fresh_install", False)),
            "update": bool(supported.get("update", False)),
            "downgrade": bool(supported.get("downgrade", False)),
            "reinstall": bool(supported.get("reinstall", False)),
        },
        "deployment_state": _release_deployment_state(conn, release_row, active_deployment_row),
    }


def _application_result(conn, application_row) -> dict:
    active_deployment_row = _get_active_deployment_row(conn, application_row)
    active_deployment = None
    operational_health = "NOT_INSTALLED"
    if active_deployment_row:
        release_row = conn.execute(
            releases.select().where(releases.c.release_id == active_deployment_row["release_id"])
        ).mappings().first()
        active_deployment = {
            "deployment_id": active_deployment_row["deployment_id"],
            "release_id": active_deployment_row["release_id"],
            "version": release_row["version"],
            "deployed_at": active_deployment_row["deployed_at"].isoformat(),
            "verification_status": active_deployment_row["verification_status"],
        }
        operational_health = "UNKNOWN"

    latest_release = conn.execute(
        releases.select()
        .where(releases.c.application_id == application_row["application_id"])
        .order_by(releases.c.imported_at.desc())
        .limit(1)
    ).mappings().first()
    canonical_path = latest_release["manifest"]["deployment"]["canonical_path"] if latest_release else None
    compose_project_name = (
        latest_release["manifest"]["deployment"]["compose_project_name"] if latest_release else None
    )

    available_release_count = conn.execute(
        sa.select(sa.func.count())
        .select_from(releases)
        .where(releases.c.application_id == application_row["application_id"])
    ).scalar()

    return {
        "id": application_row["application_id"],
        "slug": application_row["slug"],
        "name": application_row["name"],
        "description": application_row["description"],
        "canonical_path": canonical_path,
        "compose_project_name": compose_project_name,
        "active_deployment": active_deployment,
        "operational_health": operational_health,
        "available_release_count": available_release_count,
    }


def list_applications(engine) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(applications.select().order_by(applications.c.slug)).mappings().all()
        return {"items": [_application_result(conn, row) for row in rows]}


def get_application(engine, application_id: str) -> dict:
    with engine.connect() as conn:
        row = _get_application_row(conn, application_id)
        return _application_result(conn, row)


def list_application_releases(engine, application_id: str) -> dict:
    with engine.connect() as conn:
        application_row = _get_application_row(conn, application_id)
        active_deployment_row = _get_active_deployment_row(conn, application_row)
        rows = conn.execute(
            releases.select()
            .where(releases.c.application_id == application_id)
            .order_by(releases.c.imported_at)
        ).mappings().all()
        return {"items": [_release_result(conn, r, active_deployment_row) for r in rows]}


def get_release(engine, release_id: str) -> dict:
    with engine.connect() as conn:
        release_row = _get_release_row(conn, release_id)
        application_row = _get_application_row(conn, release_row["application_id"])
        active_deployment_row = _get_active_deployment_row(conn, application_row)
        return _release_result(conn, release_row, active_deployment_row)


def get_active_deployment(engine, application_id: str) -> dict | None:
    with engine.connect() as conn:
        application_row = _get_application_row(conn, application_id)
        active_deployment_row = _get_active_deployment_row(conn, application_row)
        if active_deployment_row is None:
            return None
        release_row = conn.execute(
            releases.select().where(releases.c.release_id == active_deployment_row["release_id"])
        ).mappings().first()
        return {
            "deployment_id": active_deployment_row["deployment_id"],
            "release_id": active_deployment_row["release_id"],
            "version": release_row["version"],
            "deployed_at": active_deployment_row["deployed_at"].isoformat(),
            "verification_status": active_deployment_row["verification_status"],
        }


# --- Available Actions ---


def _blocked(action: str, reasons: list[dict]) -> dict:
    return {"action": action, "allowed": False, "blocking_reasons": reasons, "requirements": []}


def _allowed(action: str, requirements: list[str] | None = None) -> dict:
    return {"action": action, "allowed": True, "blocking_reasons": [], "requirements": requirements or []}


_NO_TARGET = [{"code": "PLT-INPUT-002", "message": "No target Release was selected."}]
_NO_ACTIVE_DEPLOYMENT = [{"code": "PLT-TRANSITION-007", "message": "An active deployment is required."}]
_NOT_INSTALLED = [{"code": "PLT-APPLICATION-003", "message": "The application is not installed."}]


def _evaluate_install(active_deployment_row, target_release_row, target_storage_state) -> dict:
    if active_deployment_row:
        return _blocked("INSTALL", [{"code": "PLT-APPLICATION-002", "message": "The application is already installed."}])
    if target_release_row is None:
        return _blocked("INSTALL", _NO_TARGET)
    if target_storage_state != "AVAILABLE":
        return _blocked("INSTALL", [{"code": "PLT-RELEASE-002", "message": "The selected Release Package is not available."}])
    supported = target_release_row["manifest"]["deployment"]["supported_operations"]
    if not supported.get("fresh_install", False):
        return _blocked("INSTALL", [{"code": "PLT-TRANSITION-001", "message": "Fresh installation is not supported by this Release."}])
    return _allowed("INSTALL", requirements=["MANDATORY_VERIFICATION"])


def _evaluate_update(active_release_row, target_release_row, target_storage_state) -> dict:
    if active_release_row is None:
        return _blocked("UPDATE", _NO_ACTIVE_DEPLOYMENT)
    if target_release_row is None:
        return _blocked("UPDATE", _NO_TARGET)
    if target_release_row["release_id"] == active_release_row["release_id"]:
        return _blocked("UPDATE", [{"code": "PLT-TRANSITION-006", "message": "The target Release equals the active Release."}])
    if target_storage_state != "AVAILABLE":
        return _blocked("UPDATE", [{"code": "PLT-RELEASE-002", "message": "The selected Release Package is not available."}])
    supported = target_release_row["manifest"]["deployment"]["supported_operations"]
    if not supported.get("update", False):
        return _blocked("UPDATE", [{"code": "PLT-TRANSITION-002", "message": "Update is not supported by this Release."}])
    accepted = target_release_row["manifest"]["deployment"].get("transition", {}).get("accepted_installed_versions") or []
    if accepted and active_release_row["version"] not in accepted:
        return _blocked("UPDATE", [{"code": "PLT-TRANSITION-003", "message": "The active version is not an accepted source version for this update."}])
    return _allowed("UPDATE", requirements=["DATABASE_BACKUP", "MANDATORY_VERIFICATION"])


def _evaluate_downgrade(active_release_row, target_release_row, target_storage_state) -> dict:
    if active_release_row is None or target_release_row is None:
        return _blocked("DOWNGRADE", _NO_ACTIVE_DEPLOYMENT if active_release_row is None else _NO_TARGET)
    if target_storage_state != "AVAILABLE":
        return _blocked("DOWNGRADE", [{"code": "PLT-RELEASE-002", "message": "The selected Release Package is not available."}])
    supported = target_release_row["manifest"]["deployment"]["supported_operations"]
    if not supported.get("downgrade", False):
        return _blocked("DOWNGRADE", [{"code": "PLT-TRANSITION-004", "message": "The target Release does not support downgrade."}])
    return _allowed("DOWNGRADE", requirements=["DATABASE_BACKUP", "MANDATORY_VERIFICATION"])


def _evaluate_reinstall(active_deployment_row, target_release_row) -> dict:
    if active_deployment_row is None:
        return _blocked("REINSTALL", _NO_ACTIVE_DEPLOYMENT)
    if target_release_row is None:
        return _blocked("REINSTALL", _NO_TARGET)
    supported = target_release_row["manifest"]["deployment"]["supported_operations"]
    if not supported.get("reinstall", False):
        return _blocked("REINSTALL", [{"code": "PLT-TRANSITION-005", "message": "Reinstall is not supported by this Release."}])
    return _allowed("REINSTALL")


def _evaluate_verify(active_deployment_row) -> dict:
    if active_deployment_row is None:
        return _blocked("VERIFY", _NOT_INSTALLED)
    return _allowed("VERIFY")


def _evaluate_backup(active_deployment_row) -> dict:
    if active_deployment_row is None:
        return _blocked("BACKUP", _NOT_INSTALLED)
    return _allowed("BACKUP")


def _evaluate_recover() -> dict:
    # No failed-operation/recovery tracking exists until PL8 — always
    # unsupported for now, per the plan's own "some may always return
    # unsupported" allowance, with correct reasoning rather than a stub.
    return _blocked("RECOVER", [{"code": "PLT-RECOVERY-001", "message": "There is no failed operation to recover from."}])


def get_available_actions(engine, application_id: str, target_release_id: str | None = None) -> dict:
    with engine.connect() as conn:
        application_row = _get_application_row(conn, application_id)
        active_deployment_row = _get_active_deployment_row(conn, application_row)

        active_release_row = None
        if active_deployment_row:
            active_release_row = conn.execute(
                releases.select().where(releases.c.release_id == active_deployment_row["release_id"])
            ).mappings().first()

        target_release_row = None
        target_storage_state = None
        if target_release_id:
            target_release_row = _get_release_row(conn, target_release_id)
            if target_release_row["application_id"] != application_id:
                raise ReleaseBelongsToAnotherApplicationError(
                    "The selected Release does not belong to this application.",
                    details={"application_id": application_id, "release_id": target_release_id},
                )
            target_storage_state = _storage_state(conn, target_release_row)

        actions = [
            _evaluate_install(active_deployment_row, target_release_row, target_storage_state),
            _evaluate_update(active_release_row, target_release_row, target_storage_state),
            _evaluate_downgrade(active_release_row, target_release_row, target_storage_state),
            _evaluate_reinstall(active_deployment_row, target_release_row),
            _evaluate_verify(active_deployment_row),
            _evaluate_backup(active_deployment_row),
            _evaluate_recover(),
        ]

    return {
        "application_id": application_id,
        "active_release": (
            {"id": active_release_row["release_id"], "version": active_release_row["version"]}
            if active_release_row
            else None
        ),
        "target_release": (
            {"id": target_release_row["release_id"], "version": target_release_row["version"]}
            if target_release_row
            else None
        ),
        "actions": actions,
    }
