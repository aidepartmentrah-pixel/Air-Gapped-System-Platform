"""Release Storage path check. PL0 only proves the configured path is
reachable — scanning its contents for candidate Releases is PL2's job.
"""

from __future__ import annotations

import os

from rah_platform.errors import ReleaseStorageUnavailableError


def check_availability(release_storage_path: str) -> dict:
    if not os.path.isdir(release_storage_path):
        raise ReleaseStorageUnavailableError(
            "The configured Release Storage path does not exist or is not a directory.",
            stage="READINESS",
            details={"path": release_storage_path},
        )
    try:
        os.listdir(release_storage_path)
    except OSError as exc:
        raise ReleaseStorageUnavailableError(
            "The configured Release Storage path is not readable.",
            stage="READINESS",
            details={"path": release_storage_path, "reason": str(exc)},
        ) from exc
    return {"reachable": True, "path": release_storage_path}
