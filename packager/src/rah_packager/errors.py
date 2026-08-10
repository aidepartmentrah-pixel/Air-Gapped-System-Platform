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


class ClaudeAPIKeyMissingError(PackagerError):
    """No Anthropic API key was found — not in `ANTHROPIC_API_KEY`, not in
    the mounted credentials file. Distinct from ClaudeAuthenticationError:
    this is "never configured", not "configured wrong".
    """

    def __init__(self):
        super().__init__(
            code="PKG-CLAUDE-API-KEY-MISSING",
            message=(
                "No Anthropic API key configured. Set ANTHROPIC_API_KEY, or "
                "create ~/.rah/credentials.env on the host with an "
                "ANTHROPIC_API_KEY=... line."
            ),
        )


class ClaudeAuthenticationError(PackagerError):
    """The configured Anthropic API key was rejected by the API (wrong,
    revoked, or otherwise invalid) — the key exists, but doesn't work.
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-CLAUDE-AUTHENTICATION-FAILED",
            message=f"Anthropic API key was rejected: {detail}",
        )


class ClaudeRateLimitedError(PackagerError):
    """The Anthropic API returned 429. Transient — the key is fine."""

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-CLAUDE-RATE-LIMITED",
            message=f"Anthropic API rate limit hit: {detail}",
        )


class ClaudeConnectionError(PackagerError):
    """No response reached us at all — network/DNS failure, not an API
    error response.
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-CLAUDE-CONNECTION-FAILED",
            message=f"Could not reach the Anthropic API: {detail}",
        )


class ClaudeAPIError(PackagerError):
    """Any other non-2xx response from the Anthropic API (5xx, overload,
    malformed request, etc) not covered by a more specific error above.
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-CLAUDE-API-ERROR",
            message=f"Anthropic API error: {detail}",
        )


class ClaudeRefusalError(PackagerError):
    """Claude's safety classifier declined to answer (`stop_reason ==
    "refusal"`) — distinct from every error above, none of which are HTTP
    failures; the request succeeded but Claude chose not to comply.
    """

    def __init__(self, detail: str = ""):
        super().__init__(
            code="PKG-CLAUDE-REFUSED",
            message="Claude declined to generate engineering answers" + (f": {detail}" if detail else ""),
        )


class EngineeringAnswersSchemaError(PackagerError):
    """`.rah/engineering-answers.json` failed structural schema validation —
    either Claude's output didn't conform (a `prepare-answers` bug, since
    the Packager itself constructs the request), or a hand-edited file is
    malformed (an expected `validate-answers` outcome).
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-ENGINEERING-ANSWERS-SCHEMA-INVALID",
            message=f"Engineering Answers failed schema validation: {detail}",
        )


class EngineeringAnswersNotFoundError(PackagerError):
    """No `.rah/engineering-answers.json` exists yet — `rah prepare-answers`
    hasn't been run, or `--answers` pointed at the wrong path.
    """

    def __init__(self, answers_path: str):
        super().__init__(
            code="PKG-ENGINEERING-ANSWERS-NOT-FOUND",
            message=(
                f"No engineering answers found at {answers_path}. "
                "Run `rah prepare-answers` first."
            ),
        )


class EngineeringAnswersReadError(PackagerError):
    """The answers file exists but isn't valid JSON — distinct from a
    schema failure, which requires the JSON to at least parse first.
    """

    def __init__(self, answers_path: str, detail: str):
        super().__init__(
            code="PKG-ENGINEERING-ANSWERS-READ-FAILED",
            message=f"Could not read engineering answers at {answers_path}: {detail}",
        )


class EngineeringAnswersConflictError(PackagerError):
    """One or more answers contradict what P2 actually discovered in the
    repo right now — e.g. a claimed entrypoint script or documentation
    path that doesn't match anything `rah inspect` found. Carries the full
    list of conflicts, not just the first one.
    """

    def __init__(self, conflicts: list[str]):
        super().__init__(
            code="PKG-ENGINEERING-ANSWERS-CONFLICT",
            message="Engineering answers conflict with discovered facts: " + "; ".join(conflicts),
        )
        self.conflicts = conflicts

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["conflicts"] = self.conflicts
        return result


class EngineeringAnswersStaleError(PackagerError):
    """The answers were generated against a repository state that no
    longer matches — the Git commit moved, or something else P2 discovers
    changed without a new commit (e.g. an uncommitted edit).
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-ENGINEERING-ANSWERS-STALE",
            message=f"Engineering answers are stale: {detail}",
        )


class PlanInvalidIncrementError(PackagerError):
    """`--increment` was not one of `patch`/`minor`/`major`."""

    def __init__(self, increment: str):
        super().__init__(
            code="PKG-INPUT-INVALID-INCREMENT",
            message=f"Invalid version increment {increment!r} — must be patch, minor, or major.",
        )


class PlanProjectNotInitializedError(PackagerError):
    """`rah plan` needs a Project Version State to propose a next version
    against — distinct from P2's `packager_state: null`, which is a valid
    inspection result, not an error, because inspection doesn't need one.
    """

    def __init__(self, path: str):
        super().__init__(
            code="PKG-PLAN-PROJECT-NOT-INITIALIZED",
            message=f"Project has not been initialized (run `rah init` first): {path}",
        )


class PlanDirtySourceError(PackagerError):
    """Contract convention (release-manifest schema, `source.source_dirty`):
    a finalized Release should normally require clean source, and dirty
    source should be rejected unless an explicit exceptional policy
    permits it. V1 has no override policy — always a hard rejection.
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-PLAN-DIRTY-SOURCE-REJECTED",
            message=f"Cannot plan a Release against a dirty repository: {detail}",
        )


class PlanDuplicateVersionError(PackagerError):
    """The proposed version already exists in `release_history` — the same
    version can never be proposed twice (Releases are additive, never
    overwritten — see docs/decisions/packager-responsibility-boundaries.md).
    """

    def __init__(self, version: str):
        super().__init__(
            code="PKG-PLAN-VERSION-ALREADY-RELEASED",
            message=f"Version {version} already exists in this project's release history.",
        )


class DockerBuildFailedError(PackagerError):
    """A declared service's image failed to build — broken Dockerfile,
    missing build context, or any other real `docker build` failure.
    Carries the failing service name and a tail of the real build log so
    the failure is diagnosable from the structured error alone.
    """

    def __init__(self, service: str, detail: str, log_tail: list[str]):
        super().__init__(
            code="PKG-DOCKER-BUILD-FAILED",
            message=f"Building image for service {service!r} failed: {detail}",
        )
        self.service = service
        self.log_tail = log_tail

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["service"] = self.service
        result["log_tail"] = self.log_tail
        return result


class DockerImageExportError(PackagerError):
    """A successfully built image could not be exported/saved to a `.tar`
    archive — disk full, permissions, etc, at the filesystem level.
    """

    def __init__(self, service: str, detail: str):
        super().__init__(
            code="PKG-DOCKER-IMAGE-EXPORT-FAILED",
            message=f"Exporting image for service {service!r} failed: {detail}",
        )
        self.service = service


class EngineeringAnswersWriteError(PackagerError):
    """Writing or atomically replacing `.rah/engineering-answers.json`
    failed at the filesystem level (disk full, permissions, etc).
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-FILESYSTEM-ENGINEERING-ANSWERS-WRITE-FAILED",
            message=f"Could not write engineering answers: {detail}",
        )


class ReleaseManifestSchemaError(PackagerError):
    """A generated `release.yaml` failed schema validation against the
    real, frozen `contracts/1.0/release-manifest.schema.json`. Defensive,
    not user-facing in the normal case — the Packager itself constructs
    the manifest, so hitting this means a bug in `release_manifest.py`.
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-RELEASE-MANIFEST-SCHEMA-INVALID",
            message=f"Generated Release Manifest failed schema validation: {detail}",
        )


class ReleaseManifestIncompleteError(PackagerError):
    """Validated engineering answers are structurally valid (P3's own
    checks passed) but missing a value the Release Manifest schema
    requires outright — e.g. no `verification.entrypoint`, or
    configuration inputs declared with no template to render them into.
    Distinct from every P3 error: this is "valid but not enough to build
    a Release from", not "invalid".
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-RELEASE-MANIFEST-INCOMPLETE",
            message=f"Engineering answers are not sufficient to construct a Release: {detail}",
        )


class ReleaseModelArtifactsNotSupportedError(PackagerError):
    """`models.required: true` with declared artifacts — computing
    `baked_into_image`/`checksum` and associating each artifact with the
    Docker image it's baked into is genuinely unimplemented (matches
    HCAT's own deferral for the same reason: multi-model complexity, see
    docs/development/CURRENT.md, "Acceptance decision"). Deliberately not
    guessed or fabricated.
    """

    def __init__(self):
        super().__init__(
            code="PKG-RELEASE-MODELS-NOT-SUPPORTED",
            message=(
                "Constructing a Release with declared model artifacts is not yet "
                "supported (matches HCAT's deferral — see CURRENT.md)."
            ),
        )


class ReleaseConstructionWriteError(PackagerError):
    """Assembling the candidate Release directory (copying scripts,
    configuration, documentation, verification resources, images, or
    writing release.yaml/compose) failed at the filesystem level.
    """

    def __init__(self, detail: str):
        super().__init__(
            code="PKG-FILESYSTEM-RELEASE-CONSTRUCTION-FAILED",
            message=f"Could not construct the candidate Release: {detail}",
        )
