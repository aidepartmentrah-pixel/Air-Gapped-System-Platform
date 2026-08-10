"""Packager State facts — the "Packager State" category of P2's
`ProjectInspectionResult` (docs/development/.../1. Initial GPT Proposal.md,
P2: application identity, current version, previous Releases).

This is just reading back what P1's `rah init` (project_state.py) already
writes and validates — no new schema, no new conventions to invent.

Two failure modes, same split as Git/Docker:
- Missing `.rah/project-state.json` is not an error — the project simply
  hasn't been `rah init`-ed yet, so this category is reported as `null`.
- Present but broken (invalid JSON, or JSON that fails the P1 schema) is a
  real PackagerError — a corrupted Project Version State is a genuine
  problem, not something to silently paper over.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from rah_packager.errors import ProjectStateReadError
from rah_packager.project_state import project_state_path, validate_state


def inspect_packager_state(repo_path: str | os.PathLike) -> dict | None:
    path = Path(repo_path)
    state_path = project_state_path(path)

    if not state_path.exists():
        return None

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectStateReadError(str(state_path), str(exc)) from exc

    validate_state(state)  # raises ProjectStateSchemaError if non-conformant

    return {
        "application": state["application"],
        "current_release": state["versioning"]["current_release"],
        "next_version": state["versioning"]["next_version"],
        "release_history": state["release_history"],
    }
