"""Packager runtime configuration, loaded from environment variables.

Also resolves the Anthropic API key, in order: `ANTHROPIC_API_KEY` env var
first, then a mounted credentials file (`/config/credentials.env` by
default — the container-side path a host `~/.rah/credentials.env` gets
bind-mounted to; overridable via `RAH_CREDENTIALS_FILE` for testing and
for anyone who wants a different mount point). This mirrors the API key
never being written into `.rah/` inside a target repo — it comes from
outside every project, every time.

`anthropic_api_key_source` records which of the two won, so `rah health`
can report it without re-deriving the resolution logic elsewhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_CREDENTIALS_FILE = "/config/credentials.env"


def _credentials_file_path() -> Path:
    return Path(os.environ.get("RAH_CREDENTIALS_FILE", _DEFAULT_CREDENTIALS_FILE))


def _read_api_key_from_credentials_file() -> str | None:
    path = _credentials_file_path()
    if not path.is_file():
        return None
    # utf-8-sig: PowerShell's `Out-File -Encoding utf8` writes a BOM by
    # default; plain "utf-8" doesn't strip it, so the first line's key name
    # would silently fail to match. utf-8-sig strips a BOM if present and
    # behaves identically to utf-8 when there isn't one.
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == "ANTHROPIC_API_KEY":
            value = value.strip()
            return value or None
    return None


def _resolve_anthropic_api_key() -> tuple[str | None, str | None]:
    env_value = os.environ.get("ANTHROPIC_API_KEY")
    if env_value:
        return env_value, "env"
    file_value = _read_api_key_from_credentials_file()
    if file_value:
        return file_value, "file"
    return None, None


@dataclass(frozen=True)
class Config:
    repo_path: str | None
    output_path: str | None
    log_level: str
    anthropic_api_key: str | None
    anthropic_api_key_source: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        api_key, source = _resolve_anthropic_api_key()
        return cls(
            repo_path=os.environ.get("RAH_REPO_PATH"),
            output_path=os.environ.get("RAH_OUTPUT_PATH"),
            log_level=os.environ.get("RAH_LOG_LEVEL", "INFO"),
            anthropic_api_key=api_key,
            anthropic_api_key_source=source,
        )
