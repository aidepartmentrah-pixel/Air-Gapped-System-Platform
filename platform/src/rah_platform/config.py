"""Platform runtime configuration, loaded from environment variables.

Mirrors the Packager's `Config` pattern (`packager/src/rah_packager/config.py`):
a frozen dataclass built once from `os.environ` via `from_env()`, so tests
can construct arbitrary `Config` instances directly without touching the
environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://rah_platform:rah_platform@localhost:5432/rah_platform"
)
_DEFAULT_RELEASE_STORAGE_PATH = "/data/releases"
_DEFAULT_CONTRACTS_PATH = "/contracts/1.0"
_DEFAULT_PLATFORM_VERSION = "1.0.0"


@dataclass(frozen=True)
class Config:
    database_url: str
    release_storage_path: str
    log_level: str
    contracts_path: str = _DEFAULT_CONTRACTS_PATH
    platform_version: str = _DEFAULT_PLATFORM_VERSION

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            database_url=os.environ.get("RAH_DATABASE_URL", _DEFAULT_DATABASE_URL),
            release_storage_path=os.environ.get(
                "RAH_RELEASE_STORAGE_PATH", _DEFAULT_RELEASE_STORAGE_PATH
            ),
            log_level=os.environ.get("RAH_LOG_LEVEL", "INFO"),
            contracts_path=os.environ.get("RAH_CONTRACTS_PATH", _DEFAULT_CONTRACTS_PATH),
            platform_version=os.environ.get("RAH_PLATFORM_VERSION", _DEFAULT_PLATFORM_VERSION),
        )
