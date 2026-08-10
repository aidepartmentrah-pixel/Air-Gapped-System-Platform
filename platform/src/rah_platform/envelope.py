"""The common API response envelope, per §5.2 of the Offline Platform
Specification. Every synchronous endpoint returns this shape — success or
failure — so callers never have to branch on response structure by
endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from rah_platform.errors import PlatformError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def success_envelope(data: Any, *, warnings: list | None = None) -> dict:
    return {
        "success": True,
        "data": data,
        "warnings": warnings or [],
        "error": None,
        "request_id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
    }


def error_envelope(error: PlatformError) -> dict:
    request_id = str(uuid.uuid4())
    return {
        "success": False,
        "data": None,
        "warnings": [],
        "error": error.to_dict(request_id=request_id),
        "request_id": request_id,
        "timestamp": _now_iso(),
    }
