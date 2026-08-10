"""Repository-path and Git-repository checks shared by `rah init` (P1) and
`rah inspect` (P2) — both need "does this path exist" and "is it a Git
repository" before doing anything else.
"""

from __future__ import annotations

import os
from pathlib import Path

from rah_packager.errors import NotAGitRepositoryError, ProjectPathNotFoundError


def validate_project_path(project_path: str | os.PathLike) -> Path:
    path = Path(project_path)
    if not path.is_dir():
        raise ProjectPathNotFoundError(str(path))
    return path


def require_git_repository(path: Path) -> None:
    if not (path / ".git").exists():
        raise NotAGitRepositoryError(str(path))
