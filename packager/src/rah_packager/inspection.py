"""`rah inspect` orchestration — P2 Repository Inspection.

Assembles the `ProjectInspectionResult` category by category (Git,
Docker, Application Resources, Packager State — see
docs/development/.../1. Initial GPT Proposal.md, P2). All four categories
are implemented.
"""

from __future__ import annotations

import os

from rah_packager.application_resources_inspection import inspect_application_resources
from rah_packager.docker_inspection import inspect_docker
from rah_packager.git_inspection import inspect_git
from rah_packager.packager_state_inspection import inspect_packager_state
from rah_packager.repository import require_git_repository, validate_project_path


def inspect_project(project_path: str | os.PathLike) -> dict:
    path = validate_project_path(project_path)
    require_git_repository(path)

    return {
        "project_path": str(path),
        "git": inspect_git(path),
        "docker": inspect_docker(path),
        "application_resources": inspect_application_resources(path),
        "packager_state": inspect_packager_state(path),
    }
