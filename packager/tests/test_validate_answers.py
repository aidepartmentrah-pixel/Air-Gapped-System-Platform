import json
import subprocess

import pytest

from rah_packager.engineering_answers import compute_inspection_fingerprint
from rah_packager.errors import (
    EngineeringAnswersConflictError,
    EngineeringAnswersNotFoundError,
    EngineeringAnswersReadError,
    EngineeringAnswersSchemaError,
    EngineeringAnswersStaleError,
)
from rah_packager.inspection import inspect_project
from rah_packager.validate_answers import default_answers_path, validate_answers


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _setup_repo(tmp_path) -> dict:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "install_offline.sh").write_text("#!/bin/sh\necho install\n")
    (tmp_path / "RELEASE_NOTES.md").write_text("# Release Notes")
    (tmp_path / "INSTALL.md").write_text("# Install")
    (tmp_path / "UPDATE.md").write_text("# Update")
    (tmp_path / "RECOVERY.md").write_text("# Recovery")
    (tmp_path / "ISSUES.md").write_text("# Known Issues")

    _git(tmp_path, "init", "--quiet", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init")

    return inspect_project(tmp_path)


def _matching_answers(inspection_result: dict) -> dict:
    return {
        "schema_version": "1.0",
        "based_on": {
            "git_commit": inspection_result["git"]["commit"],
            "inspection_fingerprint": compute_inspection_fingerprint(inspection_result),
        },
        "application": {"description": "A test application."},
        "compatibility": {
            "minimum_rah_oip_version": "1.0",
            "supported_architectures": ["amd64"],
        },
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
            "installation": "INSTALL.md",
            "update": "UPDATE.md",
            "recovery": "RECOVERY.md",
            "known_issues": "ISSUES.md",
        },
    }


def _write_answers(tmp_path, answers: dict):
    answers_path = default_answers_path(tmp_path)
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text(json.dumps(answers))
    return answers_path


# --- Valid answers accepted ---


def test_valid_answers_accepted(tmp_path):
    inspection_result = _setup_repo(tmp_path)
    _write_answers(tmp_path, _matching_answers(inspection_result))

    result = validate_answers(tmp_path)

    assert result["valid"] is True
    assert result["stale"] is False


def test_repeated_validation_of_same_valid_answers_is_stable(tmp_path):
    inspection_result = _setup_repo(tmp_path)
    _write_answers(tmp_path, _matching_answers(inspection_result))

    assert validate_answers(tmp_path) == validate_answers(tmp_path)


# --- Missing answers file ---


def test_missing_answers_file_rejected(tmp_path):
    _setup_repo(tmp_path)

    with pytest.raises(EngineeringAnswersNotFoundError) as exc_info:
        validate_answers(tmp_path)
    assert exc_info.value.code == "PKG-ENGINEERING-ANSWERS-NOT-FOUND"


# --- Malformed answers rejected ---


def test_malformed_json_rejected(tmp_path):
    _setup_repo(tmp_path)
    answers_path = default_answers_path(tmp_path)
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text("{not valid json")

    with pytest.raises(EngineeringAnswersReadError) as exc_info:
        validate_answers(tmp_path)
    assert exc_info.value.code == "PKG-ENGINEERING-ANSWERS-READ-FAILED"


def test_schema_invalid_answers_rejected(tmp_path):
    inspection_result = _setup_repo(tmp_path)
    answers = _matching_answers(inspection_result)
    del answers["database"]
    _write_answers(tmp_path, answers)

    with pytest.raises(EngineeringAnswersSchemaError) as exc_info:
        validate_answers(tmp_path)
    assert exc_info.value.code == "PKG-ENGINEERING-ANSWERS-SCHEMA-INVALID"


# --- Missing required answer rejected ---


def test_missing_required_field_rejected(tmp_path):
    inspection_result = _setup_repo(tmp_path)
    answers = _matching_answers(inspection_result)
    del answers["deployment"]["supported_operations"]
    _write_answers(tmp_path, answers)

    with pytest.raises(EngineeringAnswersSchemaError):
        validate_answers(tmp_path)


# --- Conflicting deterministic fact rejected ---


def test_conflicting_entrypoint_rejected(tmp_path):
    inspection_result = _setup_repo(tmp_path)
    answers = _matching_answers(inspection_result)
    answers["deployment"]["entrypoints"]["install"] = "scripts/does_not_exist.sh"
    _write_answers(tmp_path, answers)

    with pytest.raises(EngineeringAnswersConflictError) as exc_info:
        validate_answers(tmp_path)
    assert exc_info.value.code == "PKG-ENGINEERING-ANSWERS-CONFLICT"
    assert any("does_not_exist.sh" in c for c in exc_info.value.conflicts)


def test_conflicting_documentation_path_rejected(tmp_path):
    inspection_result = _setup_repo(tmp_path)
    answers = _matching_answers(inspection_result)
    answers["documentation"]["known_issues"] = "NOT_A_REAL_FILE.md"
    _write_answers(tmp_path, answers)

    with pytest.raises(EngineeringAnswersConflictError):
        validate_answers(tmp_path)


# --- Stale answers detected ---


def test_stale_answers_detected_after_new_commit(tmp_path):
    inspection_result = _setup_repo(tmp_path)
    _write_answers(tmp_path, _matching_answers(inspection_result))

    (tmp_path / "README.md").write_text("# New file")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "--quiet", "-m", "second commit")

    with pytest.raises(EngineeringAnswersStaleError) as exc_info:
        validate_answers(tmp_path)
    assert exc_info.value.code == "PKG-ENGINEERING-ANSWERS-STALE"


def test_stale_answers_detected_when_dirty_without_new_commit(tmp_path):
    inspection_result = _setup_repo(tmp_path)
    _write_answers(tmp_path, _matching_answers(inspection_result))

    # Working tree goes dirty without a new commit — git_commit alone
    # wouldn't catch this, the inspection_fingerprint anchor does.
    (tmp_path / "scripts" / "install_offline.sh").write_text("#!/bin/sh\necho changed\n")

    with pytest.raises(EngineeringAnswersStaleError):
        validate_answers(tmp_path)
