import json
import subprocess

import jsonschema
import pytest

from rah_packager.errors import (
    ApplicationIdentityError,
    NotAGitRepositoryError,
    ProjectAlreadyInitializedError,
    ProjectPathNotFoundError,
    ProjectStateSchemaError,
    ProjectStateWriteError,
)
from rah_packager.project_state import (
    PROJECT_STATE_SCHEMA,
    init_project,
    project_state_path,
)


def _git_init(path):
    """Real `git init`, not a mock — matches P0's "real proofs" precedent."""
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)


# --- Valid Initialization ---


def test_valid_initialization_creates_project_state(tmp_path):
    _git_init(tmp_path)

    result = init_project(str(tmp_path), name="HCAT", slug="hcat", initial_version="1.0.0")

    state_path = project_state_path(tmp_path)
    assert state_path.exists()
    assert result["project_state_path"] == str(state_path)
    assert result["application"] == {"name": "HCAT", "slug": "hcat"}
    assert result["initial_version"] == "1.0.0"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state == {
        "schema_version": "1.0",
        "application": {"name": "HCAT", "slug": "hcat"},
        "versioning": {
            "strategy": "semantic",
            "current_release": None,
            "next_version": "1.0.0",
        },
        "release_history": [],
    }


def test_valid_initialization_default_initial_version(tmp_path):
    _git_init(tmp_path)

    result = init_project(str(tmp_path), name="Indicator", slug="indicator")

    assert result["initial_version"] == "1.0.0"


# --- Existing State ---


def test_second_initialization_is_safely_refused(tmp_path):
    _git_init(tmp_path)
    init_project(str(tmp_path), name="HCAT", slug="hcat")

    state_path = project_state_path(tmp_path)
    original = state_path.read_text(encoding="utf-8")

    with pytest.raises(ProjectAlreadyInitializedError) as exc_info:
        init_project(str(tmp_path), name="Something Else", slug="something-else")

    assert exc_info.value.code == "PKG-PROJECT-ALREADY-INITIALIZED"
    # refusal must not touch the existing state
    assert state_path.read_text(encoding="utf-8") == original


# --- Invalid Path ---


def test_missing_directory_raises_structured_input_error(tmp_path):
    missing = tmp_path / "does-not-exist"

    with pytest.raises(ProjectPathNotFoundError) as exc_info:
        init_project(str(missing), name="HCAT", slug="hcat")

    assert exc_info.value.code == "PKG-INPUT-PROJECT-PATH-NOT-FOUND"


# --- Non-Git Repository ---


def test_non_git_repository_fails_immediately(tmp_path):
    (tmp_path / "some_file.txt").write_text("hello")

    with pytest.raises(NotAGitRepositoryError) as exc_info:
        init_project(str(tmp_path), name="HCAT", slug="hcat")

    assert exc_info.value.code == "PKG-GIT-NOT-A-REPOSITORY"
    assert not project_state_path(tmp_path).exists()


# --- Atomicity ---


def test_failed_schema_validation_leaves_no_partial_state(tmp_path, monkeypatch):
    _git_init(tmp_path)

    def _always_fail(instance, schema):
        raise jsonschema.ValidationError("forced failure for atomicity test")

    monkeypatch.setattr("rah_packager.project_state.jsonschema.validate", _always_fail)

    with pytest.raises(ProjectStateSchemaError):
        init_project(str(tmp_path), name="HCAT", slug="hcat")

    state_path = project_state_path(tmp_path)
    assert not state_path.exists()
    assert not state_path.with_name(state_path.name + ".tmp").exists()


def test_failed_atomic_replace_leaves_no_partial_state(tmp_path, monkeypatch):
    _git_init(tmp_path)

    def _fail_replace(src, dst):
        raise OSError("simulated disk failure during rename")

    monkeypatch.setattr("rah_packager.project_state.os.replace", _fail_replace)

    with pytest.raises(ProjectStateWriteError) as exc_info:
        init_project(str(tmp_path), name="HCAT", slug="hcat")

    assert exc_info.value.code == "PKG-FILESYSTEM-PROJECT-STATE-WRITE-FAILED"
    state_path = project_state_path(tmp_path)
    assert not state_path.exists()
    assert not state_path.with_name(state_path.name + ".tmp").exists()


# --- Schema Test ---


def test_generated_state_validates_against_schema(tmp_path):
    _git_init(tmp_path)
    init_project(str(tmp_path), name="HCAT", slug="hcat")

    state = json.loads(project_state_path(tmp_path).read_text(encoding="utf-8"))
    jsonschema.validate(state, PROJECT_STATE_SCHEMA)


# --- Application identity validation ---


def test_invalid_slug_is_rejected(tmp_path):
    _git_init(tmp_path)

    with pytest.raises(ApplicationIdentityError) as exc_info:
        init_project(str(tmp_path), name="HCAT", slug="Not A Slug!")

    assert exc_info.value.code == "PKG-INPUT-INVALID-APPLICATION-IDENTITY"
    assert not project_state_path(tmp_path).exists()


def test_invalid_initial_version_is_rejected(tmp_path):
    _git_init(tmp_path)

    with pytest.raises(ApplicationIdentityError):
        init_project(str(tmp_path), name="HCAT", slug="hcat", initial_version="not-semver")

    assert not project_state_path(tmp_path).exists()
