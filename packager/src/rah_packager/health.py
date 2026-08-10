"""`rah health` — proves the P0 runtime actually works, not just that the
CLI parses arguments.

Covers three of P0's six required tests directly: Docker Connectivity,
Mounted Repository (when RAH_REPO_PATH is set), and Output (when
RAH_OUTPUT_PATH is set). Repo/output checks are optional because `rah
health` must also succeed as a pure Runtime Test before any mount is
configured at all.

Also reports Claude API credential status — whether a key was found, where
it came from, and (if found) whether it actually authenticates. Unlike
Docker connectivity, an unconfigured or invalid key never fails `rah
health` itself; it's reported, not fatal, same treatment as repo/output.
"""

from __future__ import annotations

import os
import time

from rah_packager.claude_client import validate_api_key
from rah_packager.config import Config
from rah_packager.docker_client import check_connectivity
from rah_packager.errors import PackagerError


def _check_repo_path(repo_path: str) -> dict:
    if not os.path.isdir(repo_path):
        return {"path": repo_path, "readable": False, "detail": "not a directory"}
    try:
        entries = os.listdir(repo_path)
    except OSError as exc:
        return {"path": repo_path, "readable": False, "detail": str(exc)}
    return {"path": repo_path, "readable": True, "entry_count": len(entries)}


def _check_output_path(output_path: str) -> dict:
    marker = os.path.join(output_path, ".rah-health-check")
    payload = f"rah health check at {time.time()}"
    try:
        os.makedirs(output_path, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(payload)
        with open(marker, encoding="utf-8") as f:
            round_tripped = f.read()
        os.remove(marker)
    except OSError as exc:
        return {"path": output_path, "writable": False, "detail": str(exc)}
    return {"path": output_path, "writable": round_tripped == payload}


def _check_claude_credentials(config: Config) -> dict:
    if not config.anthropic_api_key:
        return {"configured": False, "source": None, "valid": None, "error": None}

    try:
        validate_api_key(config.anthropic_api_key)
    except PackagerError as exc:
        return {
            "configured": True,
            "source": config.anthropic_api_key_source,
            "valid": False,
            "error": exc.to_dict(),
        }
    return {
        "configured": True,
        "source": config.anthropic_api_key_source,
        "valid": True,
        "error": None,
    }


def run_health_check(config: Config) -> dict:
    """Raises DockerUnavailableError (via check_connectivity) if Docker is
    unreachable — that check is mandatory. Repo/output checks are best-effort
    and included in the result only when their paths are configured. Claude
    credential status is always included but never fails the command —
    same "report, don't gate" treatment as repo/output.
    """
    report: dict = {"docker": check_connectivity(), "claude": _check_claude_credentials(config)}

    if config.repo_path:
        report["mounted_repository"] = _check_repo_path(config.repo_path)
    if config.output_path:
        report["output_directory"] = _check_output_path(config.output_path)

    return report
