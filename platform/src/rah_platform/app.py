"""The RAH Offline Installation Platform backend — PL0-PL8b.

Health (PL0), the Generic Operation Framework (PL1), Release Discovery
(PL2), Release Import & Registry (PL3), Application State & Action
Intelligence (PL4), Deployment Planning & Configuration (PL5), Fresh
Installation Execution (PL6), Verification & Host Reconciliation (PL7),
Backup & Update (PL8a), and Recovery (PL8b) so far. Every endpoint
returns the common API response envelope (§5.2).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from rah_platform import (
    application_query,
    backup,
    db,
    deployment_planning,
    health,
    installation,
    operations,
    recovery,
    release_discovery,
    release_import,
    update,
    verification,
)
from rah_platform.config import Config
from rah_platform.envelope import error_envelope, success_envelope
from rah_platform.errors import InternalError, PlatformError, RequestValidationFailedError

logger = logging.getLogger("rah_platform")


class ScanReleasesRequest(BaseModel):
    """Matches architecture §4.2 exactly — deliberately has no path field.
    `extra="forbid"` means an ordinary API caller cannot smuggle an
    arbitrary filesystem path in (PL2's "Arbitrary Directory" test): the
    request is rejected with `422` before it ever reaches `scan_releases`.
    """

    model_config = ConfigDict(extra="forbid")

    rescan_known_releases: bool = False
    include_rejected_candidates: bool = True


class ImportReleaseRequest(BaseModel):
    """Matches architecture §4.3's `expected_fingerprint` field.
    `requested_by` is accepted directly in the body rather than derived
    from an authenticated session, since no authentication mechanism is
    built anywhere in the PL0-PL9 plan — §4.23 names deriving it from
    auth as the eventual target, not something Period A Platform builds.
    """

    model_config = ConfigDict(extra="forbid")

    requested_by: str = "operator:unknown"
    expected_fingerprint: str | None = None


class PrepareUpdateRequest(BaseModel):
    """Matches architecture §4.10 — `application_id` comes from the URL
    path, not this body; the client supplies only the target."""

    model_config = ConfigDict(extra="forbid")

    target_release_id: str


class ConfigurationInputValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: object | None = None


class ValidateDeploymentInputsRequest(BaseModel):
    """Matches architecture §4.7. `release_id` comes from the URL path."""

    model_config = ConfigDict(extra="forbid")

    configuration: dict[str, ConfigurationInputValue] = {}


class SuggestAvailablePortsRequest(BaseModel):
    """Matches architecture §4.8 exactly. `exclude_application_id` is
    accepted for schema parity but unused — no notion of "ports already
    committed to another application's plan" exists yet, since nothing
    persists a plan until it's acted on (no such action exists before
    `PL6`).
    """

    model_config = ConfigDict(extra="forbid")

    count: int = 1
    minimum: int = 1024
    maximum: int = 65535
    preferred_ports: list[int] = []
    exclude_application_id: str | None = None


class InstallApplicationRequest(BaseModel):
    """Matches architecture §4.9. `target_release_id` comes from the URL
    path in this Platform's simpler endpoint style (matching PL3's
    import and PL5's installation-plan), so the body only needs
    configuration and caller identity.
    """

    model_config = ConfigDict(extra="forbid")

    configuration: dict[str, ConfigurationInputValue] = {}
    requested_by: str = "operator:unknown"


class VerifyDeploymentRequest(BaseModel):
    """Matches architecture §4.15. `application_id` comes from the URL
    path. `expected_release_id` may be omitted for `MANUAL` verification
    — the Platform infers it from the active deployment (§4.15's own
    explicit allowance, implemented by `verification._resolve_expected_release`).
    """

    model_config = ConfigDict(extra="forbid")

    expected_release_id: str | None = None
    verification_type: str = "MANUAL"
    requested_by: str = "operator:unknown"


class ReconcileApplicationStateRequest(BaseModel):
    """Matches architecture §4.17."""

    model_config = ConfigDict(extra="forbid")

    record_result: bool = True
    requested_by: str = "operator:unknown"


class CreateBackupRequest(BaseModel):
    """Matches architecture §4.18. `application_id` comes from the URL
    path. Only `backup_type: DATABASE` is implemented in Period A (see
    `backup.py`'s own docstring) — `FILES`/`FULL_DEPLOYMENT` are accepted
    at the schema level but rejected with `BackupUnsupportedError`.
    """

    model_config = ConfigDict(extra="forbid")

    backup_type: str = "DATABASE"
    verify_after_creation: bool = True
    requested_by: str = "operator:unknown"
    reason: str | None = None


class UpdateApplicationRequest(BaseModel):
    """Matches architecture §6.22. `create_backup`/`verify_after_update`
    are accepted for schema parity with the architecture's documented
    request shape; `verify_after_update` is not honored as a bypass —
    verification always runs, same as `PL6`'s install (no flag there
    either) and matching §9.17's Mandatory Verification Rule's own
    reasoning applied consistently.
    """

    model_config = ConfigDict(extra="forbid")

    target_release_id: str
    configuration_overrides: dict[str, ConfigurationInputValue] = {}
    create_backup: bool = True
    verify_after_update: bool = True
    requested_by: str = "operator:unknown"
    reason: str | None = None


class RestoreBackupRequest(BaseModel):
    """Matches architecture §4.20. `backup_id` comes from the URL path;
    `application_id` is still required in the body — the Platform verifies
    the backup belongs to *that* application (§7.23 Backup Ownership
    Rule) rather than silently inferring the application from the
    backup's own record. `verify_after_restore` is accepted for schema
    parity; verification always runs, same reasoning as
    `UpdateApplicationRequest.verify_after_update`.
    """

    model_config = ConfigDict(extra="forbid")

    application_id: str
    verify_after_restore: bool = True
    requested_by: str = "operator:unknown"
    reason: str | None = None


class RecoverApplicationRequest(BaseModel):
    """Matches architecture §4.21. `application_id` comes from the URL
    path. `recovery_mode` — only `RESTORE_PREVIOUS_STATE` is implemented
    in Period A (see `recovery.py`'s own docstring).
    """

    model_config = ConfigDict(extra="forbid")

    failed_operation_id: str
    backup_id: str
    recovery_mode: str = "RESTORE_PREVIOUS_STATE"
    requested_by: str = "operator:unknown"
    reason: str | None = None


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.from_env()
    logging.basicConfig(level=config.log_level)

    app = FastAPI(title="RAH Offline Installation Platform")
    app.state.config = config
    app.state.db_engine = db.make_engine(config.database_url)

    @app.exception_handler(PlatformError)
    async def _platform_error_handler(request, exc: PlatformError):  # noqa: ANN001
        logger.error("platform error: %s", exc.to_dict())
        return JSONResponse(status_code=exc.http_status, content=error_envelope(exc))

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(request, exc: RequestValidationError):  # noqa: ANN001
        wrapped = RequestValidationFailedError(
            "The request body failed validation.",
            details={"errors": jsonable_encoder(exc.errors())},
        )
        return JSONResponse(status_code=wrapped.http_status, content=error_envelope(wrapped))

    @app.exception_handler(Exception)
    async def _unexpected_error_handler(request, exc: Exception):  # noqa: ANN001
        logger.exception("unexpected error")
        wrapped = InternalError("An unexpected internal error occurred.", details={"reason": str(exc)})
        return JSONResponse(status_code=500, content=error_envelope(wrapped))

    @app.get("/api/v1/health/live")
    async def get_liveness():
        return success_envelope(health.liveness())

    @app.get("/api/v1/health/ready")
    async def get_readiness():
        result = health.readiness(app.state.config)
        status_code = 200 if result["status"] == "READY" else 503
        return JSONResponse(status_code=status_code, content=success_envelope(result))

    @app.get("/api/v1/operations/{operation_id}")
    async def get_operation(operation_id: str):
        return success_envelope(operations.get_operation(app.state.db_engine, operation_id))

    @app.get("/api/v1/operations/{operation_id}/events")
    async def get_operation_events(operation_id: str):
        return success_envelope(operations.get_operation_events(app.state.db_engine, operation_id))

    @app.get("/api/v1/operations/{operation_id}/logs")
    async def get_operation_logs(operation_id: str):
        return success_envelope(operations.get_operation_logs(app.state.db_engine, operation_id))

    @app.post("/api/v1/release-candidates/scan")
    async def scan_release_candidates(request: ScanReleasesRequest = ScanReleasesRequest()):
        result = release_discovery.scan_releases(app.state.db_engine, app.state.config.release_storage_path)
        return success_envelope(result)

    @app.get("/api/v1/release-candidates")
    async def list_release_candidates():
        return success_envelope(release_discovery.list_candidates(app.state.db_engine))

    @app.get("/api/v1/release-candidates/{candidate_id}")
    async def get_release_candidate(candidate_id: str):
        return success_envelope(release_discovery.get_candidate(app.state.db_engine, candidate_id))

    @app.post("/api/v1/release-candidates/{candidate_id}/import")
    async def import_release_candidate(candidate_id: str, request: ImportReleaseRequest = ImportReleaseRequest()):
        result = release_import.import_release(
            app.state.db_engine,
            app.state.config,
            candidate_id=candidate_id,
            requested_by=request.requested_by,
            expected_fingerprint=request.expected_fingerprint,
        )
        return success_envelope(result)

    @app.get("/api/v1/applications")
    async def list_applications():
        return success_envelope(application_query.list_applications(app.state.db_engine))

    @app.get("/api/v1/applications/{application_id}")
    async def get_application(application_id: str):
        return success_envelope(application_query.get_application(app.state.db_engine, application_id))

    @app.get("/api/v1/applications/{application_id}/releases")
    async def list_application_releases(application_id: str):
        return success_envelope(application_query.list_application_releases(app.state.db_engine, application_id))

    @app.get("/api/v1/releases/{release_id}")
    async def get_release(release_id: str):
        return success_envelope(application_query.get_release(app.state.db_engine, release_id))

    @app.get("/api/v1/applications/{application_id}/active-deployment")
    async def get_active_deployment(application_id: str):
        return success_envelope(application_query.get_active_deployment(app.state.db_engine, application_id))

    @app.get("/api/v1/applications/{application_id}/actions")
    async def get_available_actions(application_id: str, target_release_id: str | None = Query(default=None)):
        return success_envelope(
            application_query.get_available_actions(
                app.state.db_engine, application_id, target_release_id=target_release_id
            )
        )

    @app.post("/api/v1/releases/{release_id}/installation-plan")
    async def prepare_installation(release_id: str):
        return success_envelope(deployment_planning.prepare_installation(app.state.db_engine, release_id))

    @app.post("/api/v1/applications/{application_id}/update-plan")
    async def prepare_update(application_id: str, request: PrepareUpdateRequest):
        return success_envelope(
            deployment_planning.prepare_update(app.state.db_engine, application_id, request.target_release_id)
        )

    @app.post("/api/v1/releases/{release_id}/validate-inputs")
    async def validate_deployment_inputs(release_id: str, request: ValidateDeploymentInputsRequest = ValidateDeploymentInputsRequest()):
        configuration = {k: v.model_dump() for k, v in request.configuration.items()}
        return success_envelope(
            deployment_planning.validate_deployment_inputs(app.state.db_engine, release_id, configuration)
        )

    @app.post("/api/v1/host/ports/suggestions")
    async def suggest_available_ports(request: SuggestAvailablePortsRequest = SuggestAvailablePortsRequest()):
        return success_envelope(
            deployment_planning.suggest_available_ports(
                count=request.count,
                minimum=request.minimum,
                maximum=request.maximum,
                preferred_ports=request.preferred_ports,
            )
        )

    @app.post("/api/v1/releases/{release_id}/install", status_code=202)
    async def install_application(release_id: str, request: InstallApplicationRequest = InstallApplicationRequest()):
        configuration = {k: v.model_dump() for k, v in request.configuration.items()}
        result = installation.install_application(
            app.state.db_engine,
            app.state.config,
            release_id=release_id,
            configuration=configuration,
            requested_by=request.requested_by,
        )
        return success_envelope(result)

    @app.post("/api/v1/applications/{application_id}/verify")
    async def verify_deployment(application_id: str, request: VerifyDeploymentRequest = VerifyDeploymentRequest()):
        """§6.28 shows a `202 Accepted` response — this Platform runs
        verification synchronously instead (see `verification.py`'s own
        docstring: a handful of fast Docker/Registry checks, not a
        long-running script, so `PL6`'s async 202-then-poll pattern would
        add ceremony without buying anything). The operation is still
        recorded through the Operation Framework either way.
        """
        result = verification.verify_deployment(
            app.state.db_engine,
            app.state.config,
            application_id=application_id,
            expected_release_id=request.expected_release_id,
            verification_type=request.verification_type,
            requested_by=request.requested_by,
        )
        return success_envelope(result)

    @app.get("/api/v1/applications/{application_id}/host-state")
    async def get_host_state(
        application_id: str,
        include_docker_details: bool = Query(default=True),
        include_port_details: bool = Query(default=True),
        include_configuration_checks: bool = Query(default=True),
    ):
        """§4.16/§6.29. Read-only. The `include_*` query parameters are
        accepted for schema parity (matching `SuggestAvailablePortsRequest
        .exclude_application_id`'s own precedent) — `inspect_host_state`
        always returns full detail; there is no partial-detail mode yet.
        """
        return success_envelope(verification.inspect_host_state(app.state.db_engine, application_id))

    @app.post("/api/v1/applications/{application_id}/reconcile")
    async def reconcile_application_state(
        application_id: str, request: ReconcileApplicationStateRequest = ReconcileApplicationStateRequest()
    ):
        return success_envelope(
            verification.reconcile_application_state(
                app.state.db_engine, application_id, record_result=request.record_result
            )
        )

    @app.get("/api/v1/verifications/{verification_run_id}")
    async def get_verification_result(verification_run_id: str):
        return success_envelope(verification.get_verification_result(app.state.db_engine, verification_run_id))

    @app.post("/api/v1/applications/{application_id}/backups", status_code=202)
    async def create_backup(application_id: str, request: CreateBackupRequest = CreateBackupRequest()):
        result = backup.create_backup(
            app.state.db_engine,
            app.state.config,
            application_id=application_id,
            backup_type=request.backup_type,
            verify_after_creation=request.verify_after_creation,
            requested_by=request.requested_by,
            reason=request.reason,
        )
        return success_envelope(result)

    @app.get("/api/v1/applications/{application_id}/backups")
    async def list_backups(application_id: str):
        return success_envelope(backup.list_backups(app.state.db_engine, application_id))

    @app.get("/api/v1/backups/{backup_id}")
    async def get_backup(backup_id: str):
        return success_envelope(backup.get_backup(app.state.db_engine, backup_id))

    @app.post("/api/v1/applications/{application_id}/update", status_code=202)
    async def update_application(application_id: str, request: UpdateApplicationRequest):
        configuration_overrides = {k: v.model_dump() for k, v in request.configuration_overrides.items()}
        result = update.update_application(
            app.state.db_engine,
            app.state.config,
            application_id=application_id,
            target_release_id=request.target_release_id,
            configuration_overrides=configuration_overrides,
            create_backup=request.create_backup,
            requested_by=request.requested_by,
        )
        return success_envelope(result)

    @app.post("/api/v1/backups/{backup_id}/restore", status_code=202)
    async def restore_backup(backup_id: str, request: RestoreBackupRequest):
        result = recovery.restore_backup(
            app.state.db_engine,
            app.state.config,
            application_id=request.application_id,
            backup_id=backup_id,
            requested_by=request.requested_by,
            reason=request.reason,
        )
        return success_envelope(result)

    @app.post("/api/v1/applications/{application_id}/recover", status_code=202)
    async def recover_application(application_id: str, request: RecoverApplicationRequest):
        result = recovery.recover_application(
            app.state.db_engine,
            app.state.config,
            application_id=application_id,
            failed_operation_id=request.failed_operation_id,
            backup_id=request.backup_id,
            recovery_mode=request.recovery_mode,
            requested_by=request.requested_by,
            reason=request.reason,
        )
        return success_envelope(result)

    return app


app = create_app()
