"""Packager operational errors.

The full PKG-* operational error-code namespace is a deliberately deferred
design task (see docs/development/CURRENT.md, "Future Design Tasks") — do
not extend this module into a numbered sub-code taxonomy without that
discussion happening first. Each class here still only exists because a
real, identified failure mode needed a deterministic code — not because
the category slot existed in the architecture's list.
"""

from __future__ import annotations


class PackagerError(Exception):
    """Base class for all deterministic, structured Packager errors.

    Never let an unexpected exception escape the CLI as a raw traceback —
    P0's Failure Test requires a deterministic Packager error instead of a
    crash. Code outside this module should catch broad exceptions at the
    CLI boundary and wrap them, but should not invent new `code` values
    without a real, identified failure mode behind them.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class DockerUnavailableError(PackagerError):
    """The host Docker Engine could not be reached."""

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-RUNTIME-DOCKER-UNAVAILABLE",
            message=f"Docker Engine is unavailable: {detail}",
        )


class ProjectPathNotFoundError(PackagerError):
    """The path given to `rah init` does not exist or is not a directory."""

    def __init__(self, path: str):
        super().__init__(
            code="PKG-INPUT-PROJECT-PATH-NOT-FOUND",
            message=f"Project path does not exist or is not a directory: {path}",
        )


class NotAGitRepositoryError(PackagerError):
    """The target project has no `.git` — Version 1 requires a Git repository
    (docs/development/.../1. Initial GPT Proposal.md, P1, "Non-Git Repository":
    resolved to a hard failure, not silent partial initialization).
    """

    def __init__(self, path: str):
        super().__init__(
            code="PKG-GIT-NOT-A-REPOSITORY",
            message=f"Not a Git repository (no .git found): {path}",
        )


class ProjectAlreadyInitializedError(PackagerError):
    """`.rah/project-state.json` already exists; `rah init` refuses to touch it."""

    def __init__(self, state_path: str):
        super().__init__(
            code="PKG-PROJECT-ALREADY-INITIALIZED",
            message=f"Project is already initialized: {state_path}",
        )


class ApplicationIdentityError(PackagerError):
    """The supplied application name, slug, or initial version is invalid."""

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-INPUT-INVALID-APPLICATION-IDENTITY",
            message=detail,
        )


class ProjectStateSchemaError(PackagerError):
    """A generated Project Version State failed schema validation.

    This is a defensive check, not an expected user-facing failure — the
    Packager itself constructs the state, so hitting this means a bug in
    project_state.py, not bad user input.
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-PROJECT-STATE-SCHEMA-INVALID",
            message=f"Project Version State failed schema validation: {detail}",
        )


class ProjectStateWriteError(PackagerError):
    """Writing or atomically replacing `.rah/project-state.json` failed at
    the filesystem level (disk full, permissions, etc).
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-FILESYSTEM-PROJECT-STATE-WRITE-FAILED",
            message=f"Could not write Project Version State: {detail}",
        )


class GitInspectionError(PackagerError):
    """A `git` plumbing command failed against an already-confirmed Git
    repository (e.g. a repo with no commits yet, so `HEAD` doesn't resolve).
    Distinct from P1's NotAGitRepositoryError, which is about `.git` not
    existing at all.
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-GIT-INSPECTION-FAILED",
            message=f"Could not read Git state: {detail}",
        )


class MalformedComposeError(PackagerError):
    """A Compose file exists but could not be parsed as valid, structurally
    sound Compose YAML. A *missing* Compose file is not an error (nothing
    to inspect); a *broken* one is — P2 requires "malformed Compose
    produces stable error", not a crash or a silently empty result.
    """

    def __init__(self, compose_path: str, detail: str):
        super().__init__(
            code="PKG-DOCKER-MALFORMED-COMPOSE",
            message=f"Malformed Compose file at {compose_path}: {detail}",
        )


class ProjectStateReadError(PackagerError):
    """`.rah/project-state.json` exists but is not valid JSON. A *missing*
    state file is not an error during inspection — it just means the
    project hasn't been `rah init`-ed yet. Schema-valid-but-wrong content
    is covered by ProjectStateSchemaError instead (raised by the same
    `validate_state` P1 already uses).
    """

    def __init__(self, state_path: str, detail: str):
        super().__init__(
            code="PKG-PROJECT-STATE-READ-FAILED",
            message=f"Could not read Project Version State at {state_path}: {detail}",
        )
