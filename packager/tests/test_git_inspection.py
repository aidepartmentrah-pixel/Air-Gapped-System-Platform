import subprocess

import pytest

from rah_packager.errors import GitInspectionError
from rah_packager.git_inspection import inspect_git


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _init_repo_with_commit(path):
    _git(path, "init", "--quiet", "-b", "main")
    _git(path, "config", "user.email", "test@test.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("hello")
    _git(path, "add", "README.md")
    _git(path, "commit", "--quiet", "-m", "init")


# --- P2-T01: clean Git repository ---


def test_clean_repository_reports_clean_state(tmp_path):
    _init_repo_with_commit(tmp_path)

    facts = inspect_git(tmp_path)

    assert facts["state"] == "clean"
    assert facts["branch"] == "main"
    assert len(facts["commit"]) == 40
    assert facts["tag"] is None


# --- P2-T02: dirty Git repository ---


def test_dirty_repository_reports_dirty_state(tmp_path):
    _init_repo_with_commit(tmp_path)
    (tmp_path / "README.md").write_text("modified, uncommitted")

    facts = inspect_git(tmp_path)

    assert facts["state"] == "dirty"


def test_untracked_file_also_counts_as_dirty(tmp_path):
    _init_repo_with_commit(tmp_path)
    (tmp_path / "new_untracked_file.txt").write_text("new")

    facts = inspect_git(tmp_path)

    assert facts["state"] == "dirty"


def test_untracked_file_inside_rah_directory_does_not_count_as_dirty(tmp_path):
    # Real regression: `rah init`/`rah prepare-answers` writing their own
    # output into .rah/ must not immediately flip a clean repo dirty —
    # otherwise P3 staleness fingerprints could never match right after
    # `prepare-answers` writes its own answers file.
    _init_repo_with_commit(tmp_path)
    (tmp_path / ".rah").mkdir()
    (tmp_path / ".rah" / "engineering-answers.json").write_text("{}")

    facts = inspect_git(tmp_path)

    assert facts["state"] == "clean"


def test_modified_file_inside_rah_directory_does_not_count_as_dirty(tmp_path):
    _init_repo_with_commit(tmp_path)
    (tmp_path / ".rah").mkdir()
    (tmp_path / ".rah" / "project-state.json").write_text('{"v": 1}')
    _git(tmp_path, "add", ".rah/project-state.json")
    _git(tmp_path, "commit", "--quiet", "-m", "add project state")

    (tmp_path / ".rah" / "project-state.json").write_text('{"v": 2}')

    facts = inspect_git(tmp_path)

    assert facts["state"] == "clean"


# --- Tag detection ---


def test_tagged_commit_reports_tag(tmp_path):
    _init_repo_with_commit(tmp_path)
    _git(tmp_path, "tag", "v1.0.0")

    facts = inspect_git(tmp_path)

    assert facts["tag"] == "v1.0.0"


def test_untagged_commit_reports_no_tag(tmp_path):
    _init_repo_with_commit(tmp_path)

    facts = inspect_git(tmp_path)

    assert facts["tag"] is None


# --- Failure: repository with no commits yet ---


def test_repository_with_no_commits_raises_structured_error(tmp_path):
    _git(tmp_path, "init", "--quiet")

    with pytest.raises(GitInspectionError) as exc_info:
        inspect_git(tmp_path)

    assert exc_info.value.code == "PKG-GIT-INSPECTION-FAILED"
