"""Liveness and readiness — PL0's Required Tests, wired directly to §6.6 of
the Offline Platform Specification. Readiness inspects PostgreSQL, the
Docker Engine, and Release Storage; each failure is reported as a
structured check result rather than crashing the endpoint.
"""

from __future__ import annotations

from rah_platform import db, docker_client, release_storage
from rah_platform.config import Config
from rah_platform.errors import PlatformError


def liveness() -> dict:
    return {"status": "UP"}


def _run_check(name: str, fn) -> tuple[str, PlatformError | None]:
    try:
        fn()
    except PlatformError as exc:
        return "FAIL", exc
    return "PASS", None


def readiness(config: Config) -> dict:
    checks: dict[str, str] = {}
    failures: dict[str, dict] = {}

    for name, fn in (
        ("database", lambda: db.check_connectivity(config.database_url)),
        ("docker", docker_client.check_connectivity),
        ("release_storage", lambda: release_storage.check_availability(config.release_storage_path)),
    ):
        status, error = _run_check(name, fn)
        checks[name] = status
        if error is not None:
            failures[name] = error.to_dict()

    overall = "READY" if not failures else "NOT_READY"
    result = {"status": overall, "checks": checks}
    if failures:
        result["failures"] = failures
    return result
