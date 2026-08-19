"""Application Resources facts — the "Application Resources" category of
P2's `ProjectInspectionResult` (docs/development/.../1. Initial GPT
Proposal.md, P2: lifecycle scripts, database migration directories,
configuration templates, environment-variable names, documentation,
candidate verification resources).

Unlike Git (`.git`) and Docker (`Dockerfile`/`docker-compose.yml`), there
is no single universal filename convention for these facts. The
conventions below were not invented speculatively — they were checked
against the real, consistent naming patterns found in both P2 acceptance
apps (HCopilot and Indicator/Healthcare_reporting_system_backup):
`.env.example` / `.env.*.template` configuration templates, `scripts/`
directories (including nested ones like `release/scripts/`), `alembic`/
`migrations` directories, root-level and `documentation/`-style Markdown
docs, and `verify_*` / `*validat*`-named resources.

Everything here is presence-based discovery, not structural validation —
there is no "malformed" failure mode in this category (unlike Docker's
Compose parsing), only "found" or "not found". Categories are not
mutually exclusive: a file like `VALIDATION_CHECKLIST.md` can legitimately
appear in both `documentation` and `verification_candidates`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_IGNORED_DIR_NAMES = {
    ".git", ".rah", "node_modules", ".venv", "venv", "__pycache__",
    # Real, recurring gotcha: the Packager's own --output directory,
    # conventionally nested inside the project (see
    # docs/decisions/packager-responsibility-boundaries.md), accumulates
    # real generated content between package attempts. Left unignored,
    # every rah package run changes the inspection fingerprint it just
    # produced output from, making the *next* run see stale answers
    # immediately — a self-inflicted staleness loop, not a real change.
    "release_packager",
}

_SCRIPT_EXTENSIONS = {".sh", ".bat", ".ps1", ".py"}
_SCRIPT_DIR_NAMES = {"scripts", "script"}
_MIGRATION_DIR_NAMES = {"migrations", "alembic"}
_DOC_EXTENSION = ".md"

_ENV_VAR_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")


def _walk(repo_path: Path):
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIR_NAMES]
        yield Path(dirpath), filenames


def _relative(repo_path: Path, path: Path) -> str:
    return str(path.relative_to(repo_path).as_posix())


def _find_scripts(repo_path: Path) -> list[str]:
    found = []
    for dirpath, filenames in _walk(repo_path):
        if dirpath.name.lower() not in _SCRIPT_DIR_NAMES:
            continue
        for filename in filenames:
            if Path(filename).suffix.lower() in _SCRIPT_EXTENSIONS:
                found.append(_relative(repo_path, dirpath / filename))
    return sorted(found)


def _find_migration_directories(repo_path: Path) -> list[str]:
    found = []
    for dirpath, _filenames in _walk(repo_path):
        if dirpath.name.lower() in _MIGRATION_DIR_NAMES:
            found.append(_relative(repo_path, dirpath))
    return sorted(found)


def _is_config_template(filename: str) -> bool:
    lower = filename.lower()
    return ".env" in lower and any(marker in lower for marker in ("example", "template", "sample"))


def _find_configuration_templates(repo_path: Path) -> list[str]:
    found = []
    for dirpath, filenames in _walk(repo_path):
        for filename in filenames:
            if _is_config_template(filename):
                found.append(_relative(repo_path, dirpath / filename))
    return sorted(found)


def _extract_environment_variables(repo_path: Path, template_paths: list[str]) -> list[str]:
    names: set[str] = set()
    for rel_path in template_paths:
        try:
            text = (repo_path / rel_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _ENV_VAR_LINE.match(stripped)
            if match:
                names.add(match.group(1))
    return sorted(names)


def _find_documentation(repo_path: Path) -> list[str]:
    found = []
    for dirpath, filenames in _walk(repo_path):
        for filename in filenames:
            if filename.lower().endswith(_DOC_EXTENSION):
                found.append(_relative(repo_path, dirpath / filename))
    return sorted(found)


def _find_verification_candidates(repo_path: Path) -> list[str]:
    found = []
    for dirpath, filenames in _walk(repo_path):
        for filename in filenames:
            lower = filename.lower()
            if "verify" in lower or "valid" in lower:
                found.append(_relative(repo_path, dirpath / filename))
    return sorted(found)


def inspect_application_resources(repo_path: str | os.PathLike) -> dict:
    path = Path(repo_path)

    configuration_templates = _find_configuration_templates(path)

    return {
        "scripts": _find_scripts(path),
        "migration_directories": _find_migration_directories(path),
        "configuration_templates": configuration_templates,
        "environment_variables": _extract_environment_variables(path, configuration_templates),
        "documentation": _find_documentation(path),
        "verification_candidates": _find_verification_candidates(path),
    }
