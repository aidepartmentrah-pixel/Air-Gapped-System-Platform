"""The RAH Offline Installation Platform backend — PL0-PL4.

Health (PL0), the Generic Operation Framework (PL1), Release Discovery
(PL2), Release Import & Registry (PL3), and Application State & Action
Intelligence (PL4) so far. Every endpoint returns the common API response
envelope (§5.2).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from rah_platform import application_query, db, health, operations, release_discovery, release_import
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

    return app


app = create_app()
