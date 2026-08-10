"""Packager runtime configuration, loaded from environment variables.

P0 has nothing Contract-dependent to configure yet — this is deliberately
minimal: just the two bind-mount paths the Packager needs to prove it can
read a mounted source repository and write to a mounted output directory,
plus log level.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    repo_path: str | None
    output_path: str | None
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            repo_path=os.environ.get("RAH_REPO_PATH"),
            output_path=os.environ.get("RAH_OUTPUT_PATH"),
            log_level=os.environ.get("RAH_LOG_LEVEL", "INFO"),
        )
