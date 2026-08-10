"""The RAH Offline Installation Platform backend — PL0 slice.

Only the health endpoints exist at this stage; the Platform "does not yet
manage Applications" per the PL0 objective. Every endpoint returns the
common API response envelope (§5.2).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from rah_platform import health
from rah_platform.config import Config
from rah_platform.envelope import error_envelope, success_envelope
from rah_platform.errors import InternalError, PlatformError

logger = logging.getLogger("rah_platform")


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.from_env()
    logging.basicConfig(level=config.log_level)

    app = FastAPI(title="RAH Offline Installation Platform")
    app.state.config = config

    @app.exception_handler(PlatformError)
    async def _platform_error_handler(request, exc: PlatformError):  # noqa: ANN001
        logger.error("platform error: %s", exc.to_dict())
        return JSONResponse(status_code=500, content=error_envelope(exc))

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

    return app


app = create_app()
