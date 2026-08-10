"""`rah plan` — P4 Release Planning.

Produces a `ReleasePlan` preview (architecture §6.5) without writing
anything, anywhere — unlike P1/P3, there is no persisted output and
therefore no frozen JSON Schema to design; the returned dict is an
ephemeral preview, the same treatment P2's `ProjectInspectionResult`
already gets.

Answers the question "exactly what Release am I about to build?" by
reading three things that already exist and combining them:
- P1's Project Version State (current version, release history) —
  via P2's `packager_state` inspection category, not a second read.
- P2's `ProjectInspectionResult` (Git cleanliness, Docker services).
- P3's Engineering Answers, validated fresh via `validate_answers()` —
  its existing errors (not found / schema-invalid / conflicting / stale)
  become this module's "Missing Engineering Answers" gate for free,
  rather than being re-implemented here.

Four blocking conditions, each a real structured error (user-confirmed:
no override policy for dirty source in V1 — always a hard rejection):
project never initialized, dirty Git state, proposed version already in
release history, and (via `validate_answers`) missing/invalid/stale
engineering answers.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from rah_packager.errors import (
    PlanDirtySourceError,
    PlanDuplicateVersionError,
    PlanInvalidIncrementError,
    PlanProjectNotInitializedError,
)
from rah_packager.inspection import inspect_project
from rah_packager.repository import require_git_repository, validate_project_path
from rah_packager.validate_answers import default_answers_path, validate_answers

# The Contract version this build of the Packager targets — mirrors the
# SCHEMA_VERSION constant convention in project_state.py / engineering_answers.py.
RELEASE_CONTRACT_VERSION = "1.0"

_INCREMENTS = ("patch", "minor", "major")
_SEMVER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

# release-layout.yaml's required_structure, minus release.yaml/checksums/
# compliance (those are Packager-generated at packaging time, not
# "expected artifacts" an engineer would recognize as their own resources)
# and minus database/ (conditional — added back in only when the
# engineering answers declare database.required: true).
_UNCONDITIONAL_RELEASE_DIRECTORIES = (
    "compose/",
    "docker-images/",
    "scripts/",
    "configuration/",
    "documentation/",
    "verification/",
)


def _bump_version(version: str, increment: str) -> str:
    match = _SEMVER_PATTERN.match(version)
    major, minor, patch = (int(part) for part in match.groups())
    if increment == "major":
        return f"{major + 1}.0.0"
    if increment == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def prepare_plan(
    project_path: str | os.PathLike,
    increment: str = "patch",
    answers_path: str | os.PathLike | None = None,
) -> dict:
    if increment not in _INCREMENTS:
        raise PlanInvalidIncrementError(increment)

    path = validate_project_path(project_path)
    require_git_repository(path)

    inspection_result = inspect_project(path)
    packager_state = inspection_result["packager_state"]
    if packager_state is None:
        raise PlanProjectNotInitializedError(str(path))

    if inspection_result["git"]["state"] != "clean":
        raise PlanDirtySourceError(
            f"repository at {path} has uncommitted changes"
        )

    current_release = packager_state["current_release"]
    if current_release is None:
        # No prior Release to bump from — the proposed version is simply
        # the one chosen at `rah init` time (project_state.py's "State
        # Before the First Release" shape).
        proposed_version = packager_state["next_version"]
    else:
        proposed_version = _bump_version(current_release, increment)

    already_released = {entry["version"] for entry in packager_state["release_history"]}
    if proposed_version in already_released:
        raise PlanDuplicateVersionError(proposed_version)

    # Reuses P3's full validation (schema + consistency + staleness) rather
    # than re-deriving any of it here.
    validate_answers(path, answers_path)
    resolved_answers_path = (
        Path(answers_path) if answers_path else default_answers_path(path)
    )
    answers = json.loads(resolved_answers_path.read_text(encoding="utf-8"))

    application = packager_state["application"]
    docker_services = inspection_result["docker"]["services"]

    expected_docker_images = [
        {"service": service["name"], "image": service.get("image")}
        for service in docker_services
    ]
    required_scripts = sorted(set(answers["deployment"]["entrypoints"].values()))
    required_configuration_resources = answers["configuration"]["inputs"]

    expected_release_directories = list(_UNCONDITIONAL_RELEASE_DIRECTORIES)
    if answers["database"]["required"]:
        expected_release_directories.append("database/")
    expected_release_directories.sort()

    return {
        "application": application,
        "current_release": current_release,
        "proposed_version": proposed_version,
        "increment": increment if current_release is not None else None,
        "release_contract_version": RELEASE_CONTRACT_VERSION,
        "release_directory_name": f"{application['name']}_Release_{proposed_version}",
        "expected_docker_images": expected_docker_images,
        "expected_release_directories": expected_release_directories,
        "required_scripts": required_scripts,
        "required_configuration_resources": required_configuration_resources,
        "may_proceed": True,
    }
