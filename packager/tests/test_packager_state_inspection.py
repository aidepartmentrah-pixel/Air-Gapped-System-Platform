import json
import subprocess

import pytest

from rah_packager.errors import ProjectStateReadError, ProjectStateSchemaError
from rah_packager.packager_state_inspection import inspect_packager_state
from rah_packager.project_state import init_project, project_state_path


def _git_init(path):
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)


# --- Not yet initialized: missing is not an error ---


def test_uninitialized_project_reports_none(tmp_path):
    _git_init(tmp_path)

    result = inspect_packager_state(tmp_path)

    assert result is None


# --- Valid state read back correctly ---


def test_initialized_project_reports_packager_state(tmp_path):
    _git_init(tmp_path)
    init_project(str(tmp_path), name="HCAT", slug="hcat", initial_version="1.0.0")

    result = inspect_packager_state(tmp_path)

    assert result == {
        "application": {"name": "HCAT", "slug": "hcat"},
        "current_release": None,
        "next_version": "1.0.0",
        "release_history": [],
    }


# --- Corrupted JSON is a real error, not silently ignored ---


def test_corrupted_json_raises_structured_error(tmp_path):
    _git_init(tmp_path)
    init_project(str(tmp_path), name="HCAT", slug="hcat")

    state_path = project_state_path(tmp_path)
    state_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ProjectStateReadError) as exc_info:
        inspect_packager_state(tmp_path)

    assert exc_info.value.code == "PKG-PROJECT-STATE-READ-FAILED"


# --- Schema-invalid content is a real error, not silently ignored ---


def test_schema_invalid_state_raises_structured_error(tmp_path):
    _git_init(tmp_path)
    init_project(str(tmp_path), name="HCAT", slug="hcat")

    state_path = project_state_path(tmp_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    del state["schema_version"]  # required field, per architecture §12
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ProjectStateSchemaError):
        inspect_packager_state(tmp_path)
