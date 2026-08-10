import json
import subprocess

import pytest

from rah_packager.engineering_answers import compute_inspection_fingerprint
from rah_packager.errors import (
    EngineeringAnswersNotFoundError,
    EngineeringAnswersStaleError,
    PlanDirtySourceError,
    PlanDuplicateVersionError,
    PlanInvalidIncrementError,
    PlanProjectNotInitializedError,
)
from rah_packager.inspection import inspect_project
from rah_packager.project_state import build_initial_state, project_state_path
from rah_packager.release_plan import prepare_plan
from rah_packager.validate_answers import default_answers_path


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _commit_all(path, message):
    _git(path, "add", ".")
    _git(path, "commit", "--quiet", "-m", message)


def _init_repo(path):
    (path / "scripts").mkdir()
    (path / "scripts" / "install_offline.sh").write_text("#!/bin/sh\necho install\n")
    (path / "RELEASE_NOTES.md").write_text("# Release Notes")

    _git(path, "init", "--quiet", "-b", "main")
    _git(path, "config", "user.email", "test@test.com")
    _git(path, "config", "user.name", "test")
    _commit_all(path, "init")


def _write_state(path, state: dict):
    state_path = project_state_path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state))


def _matching_answers(inspection_result: dict, **overrides) -> dict:
    answers = {
        "schema_version": "1.0",
        "based_on": {
            "git_commit": inspection_result["git"]["commit"],
            "inspection_fingerprint": compute_inspection_fingerprint(inspection_result),
        },
        "application": {"description": "A test application."},
        "compatibility": {"minimum_rah_oip_version": "1.0", "supported_architectures": ["amd64"]},
        "deployment": {
            "entrypoints": {"install": "scripts/install_offline.sh"},
            "supported_operations": {"fresh_install": True},
        },
        "configuration": {"inputs": []},
        "database": {"required": False},
        "persistent_state": {"preserve_during_update": []},
        "offline_requirements": {
            "public_internet_required": False,
            "public_registry_required": False,
            "public_cdn_required": False,
            "online_model_registry_required": False,
        },
        "models": {"required": False},
        "client": {"preparation_required": False, "https_required": False},
        "verification": {"required_checks": []},
        "documentation": {
            "release_notes": "RELEASE_NOTES.md",
            "installation": "RELEASE_NOTES.md",
            "update": "RELEASE_NOTES.md",
            "recovery": "RELEASE_NOTES.md",
            "known_issues": "RELEASE_NOTES.md",
        },
    }
    answers.update(overrides)
    return answers


def _write_answers(path, answers: dict):
    answers_path = default_answers_path(path)
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text(json.dumps(answers))


def _setup_first_release_repo(tmp_path):
    """A freshly `rah init`-ed project — no Release yet. Packager state and
    engineering answers deliberately stay uncommitted: `.rah/` is excluded
    from the Git dirty-check (see git_inspection.py), so this is still a
    "clean" repo as far as `rah plan` is concerned, and `based_on` stays
    pinned to `_init_repo`'s one real commit throughout.
    """
    _init_repo(tmp_path)
    state = build_initial_state("Test App", "test-app", "1.0.0")
    _write_state(tmp_path, state)
    inspection_result = inspect_project(tmp_path)
    _write_answers(tmp_path, _matching_answers(inspection_result))
    return inspection_result


def _setup_repo_with_prior_release(tmp_path, current_release="1.0.0"):
    _init_repo(tmp_path)
    state = build_initial_state("Test App", "test-app", current_release)
    state["versioning"]["current_release"] = current_release
    state["release_history"] = [
        {
            "version": current_release,
            "created_at": "2026-01-01T00:00:00Z",
            "source": {"git_commit": "0" * 40, "git_tag": f"v{current_release}"},
            "summary": "first release",
        }
    ]
    _write_state(tmp_path, state)
    inspection_result = inspect_project(tmp_path)
    _write_answers(tmp_path, _matching_answers(inspection_result))
    return inspection_result


# --- Before the first Release: proposed version is the stored next_version ---


def test_first_release_uses_stored_next_version(tmp_path):
    _setup_first_release_repo(tmp_path)

    plan = prepare_plan(tmp_path)

    assert plan["current_release"] is None
    assert plan["proposed_version"] == "1.0.0"
    assert plan["increment"] is None
    assert plan["may_proceed"] is True


# --- Patch / Minor / Major increment ---


def test_patch_increment(tmp_path):
    _setup_repo_with_prior_release(tmp_path, current_release="1.2.3")
    plan = prepare_plan(tmp_path, increment="patch")
    assert plan["proposed_version"] == "1.2.4"
    assert plan["increment"] == "patch"


def test_minor_increment(tmp_path):
    _setup_repo_with_prior_release(tmp_path, current_release="1.2.3")
    plan = prepare_plan(tmp_path, increment="minor")
    assert plan["proposed_version"] == "1.3.0"


def test_major_increment(tmp_path):
    _setup_repo_with_prior_release(tmp_path, current_release="1.2.3")
    plan = prepare_plan(tmp_path, increment="major")
    assert plan["proposed_version"] == "2.0.0"


def test_invalid_increment_rejected(tmp_path):
    _setup_repo_with_prior_release(tmp_path)
    with pytest.raises(PlanInvalidIncrementError) as exc_info:
        prepare_plan(tmp_path, increment="epoch")
    assert exc_info.value.code == "PKG-INPUT-INVALID-INCREMENT"


# --- Duplicate version rejected ---


def test_duplicate_version_rejected(tmp_path):
    # current_release "1.2.3", but release_history already contains "1.2.4"
    # too (e.g. a prior aborted attempt) — patch-incrementing must be
    # rejected since it collides with existing history.
    _init_repo(tmp_path)
    state = build_initial_state("Test App", "test-app", "1.2.3")
    state["versioning"]["current_release"] = "1.2.3"
    state["release_history"] = [
        {
            "version": "1.2.3",
            "created_at": "2026-01-01T00:00:00Z",
            "source": {"git_commit": "0" * 40, "git_tag": "v1.2.3"},
            "summary": "first",
        },
        {
            "version": "1.2.4",
            "created_at": "2026-01-02T00:00:00Z",
            "source": {"git_commit": "1" * 40, "git_tag": "v1.2.4"},
            "summary": "second",
        },
    ]
    _write_state(tmp_path, state)
    inspection_result = inspect_project(tmp_path)
    _write_answers(tmp_path, _matching_answers(inspection_result))

    with pytest.raises(PlanDuplicateVersionError) as exc_info:
        prepare_plan(tmp_path, increment="patch")
    assert exc_info.value.code == "PKG-PLAN-VERSION-ALREADY-RELEASED"


# --- Dirty Git state rejected, no override ---


def test_dirty_git_state_rejected(tmp_path):
    _setup_first_release_repo(tmp_path)
    (tmp_path / "scripts" / "install_offline.sh").write_text("#!/bin/sh\necho changed\n")

    with pytest.raises(PlanDirtySourceError) as exc_info:
        prepare_plan(tmp_path)
    assert exc_info.value.code == "PKG-PLAN-DIRTY-SOURCE-REJECTED"


# --- Missing engineering answers blocks the plan ---


def test_missing_engineering_answers_blocks_plan(tmp_path):
    _init_repo(tmp_path)
    state = build_initial_state("Test App", "test-app", "1.0.0")
    _write_state(tmp_path, state)

    with pytest.raises(EngineeringAnswersNotFoundError):
        prepare_plan(tmp_path)


def test_stale_engineering_answers_blocks_plan(tmp_path):
    inspection_result = _setup_first_release_repo(tmp_path)
    (tmp_path / "README.md").write_text("# New file")
    _commit_all(tmp_path, "unrelated new commit")

    with pytest.raises(EngineeringAnswersStaleError):
        prepare_plan(tmp_path)


# --- Invalid / uninitialized project state blocks the plan ---


def test_uninitialized_project_blocks_plan(tmp_path):
    _init_repo(tmp_path)

    with pytest.raises(PlanProjectNotInitializedError) as exc_info:
        prepare_plan(tmp_path)
    assert exc_info.value.code == "PKG-PLAN-PROJECT-NOT-INITIALIZED"


# --- Full plan content, once all gates pass ---


def test_plan_reports_expected_release_shape(tmp_path):
    _setup_first_release_repo(tmp_path)

    plan = prepare_plan(tmp_path)

    assert plan["application"] == {"name": "Test App", "slug": "test-app"}
    assert plan["release_contract_version"] == "1.0"
    assert plan["release_directory_name"] == "Test App_Release_1.0.0"
    assert plan["required_scripts"] == ["scripts/install_offline.sh"]
    assert plan["required_configuration_resources"] == []
    assert "database/" not in plan["expected_release_directories"]
    assert plan["expected_release_directories"] == sorted(
        ["compose/", "docker-images/", "scripts/", "configuration/", "documentation/", "verification/"]
    )


def test_plan_includes_database_directory_when_required(tmp_path):
    # .rah/engineering-answers.json isn't part of what based_on's git_commit
    # or inspection_fingerprint cover (it's excluded from dirty-detection
    # and application_resources never walks .rah/), so overwriting it here
    # keeps the already-committed `based_on` anchors valid — no new commit
    # needed.
    inspection_result = _setup_first_release_repo(tmp_path)
    answers = _matching_answers(inspection_result)
    answers["database"] = {"required": True, "platform": "postgresql"}
    _write_answers(tmp_path, answers)

    plan = prepare_plan(tmp_path)

    assert "database/" in plan["expected_release_directories"]
