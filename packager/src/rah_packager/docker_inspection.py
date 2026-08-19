"""Docker facts — the "Docker" category of P2's `ProjectInspectionResult`
(docs/development/.../1. Initial GPT Proposal.md, P2: Dockerfiles, Compose
files, services, image names, build contexts).

Two failure modes, handled differently:
- Missing (no Dockerfile, no Compose file) is not an error — reported as
  an empty list / `null`, same as `git_inspection.py`'s "no tag" handling.
- Malformed (a Compose file that exists but doesn't parse as valid,
  structurally sound YAML) is a real PackagerError — P2 requires "malformed
  Compose produces stable error", not a crash or a silently empty result.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from rah_packager.errors import MalformedComposeError

# Directories that are never worth walking into looking for Dockerfiles —
# pruned before descent (not just filtered after) so a real repo's
# node_modules/.venv doesn't turn this into a slow, pointless full walk.
_IGNORED_DIR_NAMES = {
    ".git", ".rah", "node_modules", ".venv", "venv", "__pycache__",
    # Same reasoning as application_resources_inspection.py's copy of this
    # set: the Packager's own --output directory, conventionally nested
    # inside the project, must never feed back into its own inspection.
    "release_packager",
}

_COMPOSE_FILE_NAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)


def _find_dockerfiles(repo_path: Path) -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIR_NAMES]
        for filename in filenames:
            if filename == "Dockerfile" or filename.startswith("Dockerfile."):
                full_path = Path(dirpath) / filename
                found.append(str(full_path.relative_to(repo_path).as_posix()))
    return sorted(found)


def _find_compose_file(repo_path: Path) -> Path | None:
    for name in _COMPOSE_FILE_NAMES:
        candidate = repo_path / name
        if candidate.is_file():
            return candidate
    return None


def _parse_compose(compose_path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MalformedComposeError(str(compose_path), str(exc)) from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise MalformedComposeError(
            str(compose_path), "top level of a Compose file must be a mapping"
        )
    return raw


def _extract_services(compose_data: dict[str, Any], compose_path: Path) -> list[dict]:
    services_section = compose_data.get("services") or {}
    if not isinstance(services_section, dict):
        raise MalformedComposeError(str(compose_path), "'services' must be a mapping")

    services = []
    for name, definition in services_section.items():
        definition = definition or {}
        image = definition.get("image")

        build = definition.get("build")
        build_info = None
        if isinstance(build, str):
            build_info = {"context": build, "dockerfile": None}
        elif isinstance(build, dict):
            build_info = {"context": build.get("context"), "dockerfile": build.get("dockerfile")}

        services.append({"name": name, "image": image, "build": build_info})
    return services


def inspect_docker(repo_path: str | Path) -> dict:
    path = Path(repo_path)

    dockerfiles = _find_dockerfiles(path)
    compose_path = _find_compose_file(path)

    if compose_path is None:
        return {"dockerfiles": dockerfiles, "compose_file": None, "services": []}

    compose_data = _parse_compose(compose_path)
    services = _extract_services(compose_data, compose_path)

    return {
        "dockerfiles": dockerfiles,
        "compose_file": str(compose_path.relative_to(path).as_posix()),
        "services": services,
    }
