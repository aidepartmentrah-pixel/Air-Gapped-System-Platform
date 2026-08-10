"""Project Version State — `.rah/project-state.json`.

Implements P1 (Project Initialization). The JSON Schema and the
application-level validation rules referenced here are not designed in
this file — they are copied verbatim from the frozen architecture,
docs/architecture/4. Stage 4 — Choose Implementation Mechanisms.md,
Part 1 — Project Version State, §12 (JSON Schema) and §13 (Application-
Level Validation Rules). If the schema ever needs to change, that is an
architecture decision, not something to hand-edit here.

Write safety follows §14: write a `.tmp` file, validate it, then replace
the real file atomically (`os.replace`) — `project-state.json` itself is
never observed in a partially written or invalid state.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import jsonschema

from rah_packager.errors import (
    ApplicationIdentityError,
    ProjectAlreadyInitializedError,
    ProjectStateSchemaError,
    ProjectStateWriteError,
)
from rah_packager.repository import require_git_repository, validate_project_path

SCHEMA_VERSION = "1.0"
DEFAULT_INITIAL_VERSION = "1.0.0"
RAH_DIR_NAME = ".rah"
STATE_FILE_NAME = "project-state.json"

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEMVER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

# Verbatim from architecture §12.
PROJECT_STATE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://rah.local/schemas/project-state.schema.json",
    "title": "RAH Project Version State",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "application", "versioning", "release_history"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "application": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "slug"],
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 120},
                "slug": {
                    "type": "string",
                    "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                    "minLength": 1,
                    "maxLength": 80,
                },
            },
        },
        "versioning": {
            "type": "object",
            "additionalProperties": False,
            "required": ["strategy", "current_release", "next_version"],
            "properties": {
                "strategy": {"type": "string", "const": "semantic"},
                "current_release": {
                    "oneOf": [
                        {
                            "type": "string",
                            "pattern": "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
                        },
                        {"type": "null"},
                    ]
                },
                "next_version": {
                    "type": "string",
                    "pattern": "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
                },
            },
        },
        "release_history": {
            "type": "array",
            "items": {"$ref": "#/$defs/releaseHistoryEntry"},
        },
    },
    "$defs": {
        "releaseHistoryEntry": {
            "type": "object",
            "additionalProperties": False,
            "required": ["version", "created_at", "source", "summary"],
            "properties": {
                "version": {
                    "type": "string",
                    "pattern": "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
                },
                "created_at": {"type": "string", "format": "date-time"},
                "source": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["git_commit", "git_tag"],
                    "properties": {
                        "git_commit": {"type": "string", "pattern": "^[0-9a-fA-F]{40}$"},
                        "git_tag": {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "pattern": "^v(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
                                },
                                {"type": "null"},
                            ]
                        },
                    },
                },
                "summary": {"type": "string", "minLength": 1, "maxLength": 1000},
            },
        }
    },
}


def project_state_path(project_path: str | os.PathLike) -> Path:
    return Path(project_path) / RAH_DIR_NAME / STATE_FILE_NAME


def _validate_identity(name: str, slug: str, initial_version: str) -> None:
    if not name or not name.strip():
        raise ApplicationIdentityError("Application name must not be empty.")
    if len(name) > 120:
        raise ApplicationIdentityError("Application name must be 120 characters or fewer.")
    if not _SLUG_PATTERN.match(slug):
        raise ApplicationIdentityError(
            f"Application slug {slug!r} is invalid — it must use lowercase letters, "
            "numbers, and hyphens only (e.g. 'hcat', 'patient-complaints')."
        )
    if not _SEMVER_PATTERN.match(initial_version):
        raise ApplicationIdentityError(
            f"Initial version {initial_version!r} is not a valid semantic version "
            "(MAJOR.MINOR.PATCH)."
        )


def build_initial_state(name: str, slug: str, initial_version: str) -> dict:
    """The "State Before the First Release" shape from architecture §9:
    empty history, no current release yet, the given version proposed next.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "application": {"name": name, "slug": slug},
        "versioning": {
            "strategy": "semantic",
            "current_release": None,
            "next_version": initial_version,
        },
        "release_history": [],
    }


def validate_state(state: dict) -> None:
    try:
        jsonschema.validate(state, PROJECT_STATE_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ProjectStateSchemaError(exc.message) from exc


def _write_state_atomically(state_path: Path, state: dict) -> None:
    """§14 Write Safety: write `.tmp`, validate it, replace atomically.
    `state_path` itself is only ever touched by the final `os.replace`, so a
    failure at any earlier step leaves no trace on the real filename.
    """
    tmp_path = state_path.with_name(state_path.name + ".tmp")
    payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(payload, encoding="utf-8")
        validate_state(json.loads(tmp_path.read_text(encoding="utf-8")))
        os.replace(tmp_path, state_path)
    except OSError as exc:
        raise ProjectStateWriteError(str(exc)) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def init_project(
    project_path: str | os.PathLike,
    name: str,
    slug: str,
    initial_version: str = DEFAULT_INITIAL_VERSION,
) -> dict:
    """`rah init`. Raises a PackagerError subclass on any failure; never
    leaves a malformed `.rah/project-state.json` behind (see
    `_write_state_atomically`).
    """
    path = validate_project_path(project_path)
    require_git_repository(path)

    state_path = project_state_path(path)
    if state_path.exists():
        raise ProjectAlreadyInitializedError(str(state_path))

    _validate_identity(name, slug, initial_version)

    state = build_initial_state(name, slug, initial_version)
    _write_state_atomically(state_path, state)

    return {
        "application": state["application"],
        "project_state_path": str(state_path),
        "initial_version": initial_version,
        "schema_valid": True,
    }
