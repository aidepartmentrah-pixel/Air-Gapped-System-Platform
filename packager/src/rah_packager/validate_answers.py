"""`rah validate-answers` — P3 subtask 3.

Three checks, in order, each a distinct failure mode (see
docs/decisions/engineering-answers-and-staleness.md):

1. Schema (structural) — a broken file can't be meaningfully cross-checked,
   so this runs first.
2. Cross-field consistency against the *current* `ProjectInspectionResult`
   — catches an answer claiming a script/doc path P2 never actually found.
3. Staleness — both `based_on` anchors recomputed against the current repo
   and compared; either mismatching means the answers may not reflect the
   repo anymore.

Deterministic throughout — no Claude API call anywhere in this module.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from rah_packager.engineering_answers import (
    compute_inspection_fingerprint,
    validate_engineering_answers_schema,
)
from rah_packager.errors import (
    EngineeringAnswersConflictError,
    EngineeringAnswersNotFoundError,
    EngineeringAnswersReadError,
    EngineeringAnswersStaleError,
)
from rah_packager.inspection import inspect_project
from rah_packager.repository import require_git_repository, validate_project_path

DEFAULT_ANSWERS_FILENAME = "engineering-answers.json"

# (path-in-answers-dict) for every field that must name a script P2 actually
# found in application_resources.scripts, or a documentation file it found
# in application_resources.documentation. Kept as flat tuples rather than a
# generic walker — the set of checkable fields is fixed by the schema, not
# something that needs to grow dynamically.
_SCRIPT_FIELDS: list[tuple[str, ...]] = [
    ("deployment", "entrypoints", "install"),
    ("deployment", "entrypoints", "update"),
    ("deployment", "entrypoints", "verify"),
    ("deployment", "entrypoints", "backup"),
    ("deployment", "entrypoints", "restore"),
    ("database", "initialization", "entrypoint"),
    ("database", "migration", "entrypoint"),
    ("database", "backup_before_update", "entrypoint"),
    ("database", "recovery", "entrypoint"),
    ("verification", "entrypoint"),
]

_DOCUMENTATION_FIELDS: list[tuple[str, ...]] = [
    ("documentation", "release_notes"),
    ("documentation", "installation"),
    ("documentation", "update"),
    ("documentation", "recovery"),
    ("documentation", "known_issues"),
]


def default_answers_path(project_path: str | os.PathLike) -> Path:
    return Path(project_path) / ".rah" / DEFAULT_ANSWERS_FILENAME


def _load_answers(answers_path: Path) -> dict:
    if not answers_path.is_file():
        raise EngineeringAnswersNotFoundError(str(answers_path))
    try:
        return json.loads(answers_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineeringAnswersReadError(str(answers_path), str(exc)) from exc


def _dig(answers: dict, path: tuple[str, ...]):
    node = answers
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _check_consistency(answers: dict, current_inspection: dict) -> list[str]:
    resources = current_inspection.get("application_resources") or {}
    known_scripts = set(resources.get("scripts") or [])
    known_docs = set(resources.get("documentation") or [])

    conflicts = []

    for path in _SCRIPT_FIELDS:
        value = _dig(answers, path)
        if value is not None and value not in known_scripts:
            field = ".".join(path)
            conflicts.append(f"{field} = {value!r} does not match any script P2 discovered")

    for path in _DOCUMENTATION_FIELDS:
        value = _dig(answers, path)
        if value is not None and value not in known_docs:
            field = ".".join(path)
            conflicts.append(
                f"{field} = {value!r} does not match any documentation file P2 discovered"
            )

    return conflicts


def _check_staleness(answers: dict, current_inspection: dict) -> None:
    based_on = answers.get("based_on") or {}
    current_commit = (current_inspection.get("git") or {}).get("commit")
    current_fingerprint = compute_inspection_fingerprint(current_inspection)

    if based_on.get("git_commit") != current_commit:
        raise EngineeringAnswersStaleError(
            f"answers were generated against commit {based_on.get('git_commit')}, "
            f"repo is now at {current_commit}"
        )
    if based_on.get("inspection_fingerprint") != current_fingerprint:
        raise EngineeringAnswersStaleError(
            "answers were generated against a different repository state "
            "(inspection fingerprint mismatch) even though the Git commit matches"
        )


def validate_answers(
    project_path: str | os.PathLike,
    answers_path: str | os.PathLike | None = None,
) -> dict:
    path = validate_project_path(project_path)
    require_git_repository(path)

    resolved_answers_path = Path(answers_path) if answers_path else default_answers_path(path)

    answers = _load_answers(resolved_answers_path)
    validate_engineering_answers_schema(answers)

    current_inspection = inspect_project(path)

    conflicts = _check_consistency(answers, current_inspection)
    if conflicts:
        raise EngineeringAnswersConflictError(conflicts)

    _check_staleness(answers, current_inspection)

    return {"answers_path": str(resolved_answers_path), "valid": True, "stale": False}
