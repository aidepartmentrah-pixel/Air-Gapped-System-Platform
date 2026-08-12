"""The Platform error object, per `docs/architecture/4.7. Stage 4 — Offline
Platform Specification.md` §8 (Platform Error Contract) — codes, categories,
and field shape are copied verbatim from the frozen architecture, not
invented here. Only the categories/codes PL0 actually raises are wired up
as classes; the rest of the `PLT-*` catalog belongs to the slices that
raise them.
"""

from __future__ import annotations


class PlatformError(Exception):
    code: str
    category: str
    retryable: bool = False
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        details: dict | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.details = details or {}
        if retryable is not None:
            self.retryable = retryable

    def to_dict(
        self,
        *,
        request_id: str | None = None,
        operation_id: str | None = None,
        log_reference: str | None = None,
    ) -> dict:
        return {
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "stage": self.stage,
            "retryable": self.retryable,
            "details": self.details,
            "request_id": request_id,
            "operation_id": operation_id,
            "log_reference": log_reference,
        }


class DatabaseConnectionError(PlatformError):
    code = "PLT-DATABASE-003"
    category = "DATABASE"
    retryable = True
    http_status = 503


class MigrationFailedError(PlatformError):
    """§8.19's own category comment: "These errors may refer either to
    the Platform Registry or the application database" — `PLT-DATABASE-002`
    is deliberately dual-use by the architecture's own design, not a
    reuse-of-convenience. `PL0` raises this for the Platform's own Alembic
    migrations; `PL8` (`update.py`) raises the same class for a Release's
    declared `database.migration.entrypoint` script failing during a real
    update — both are genuinely "Migration failed," just at different
    layers.
    """

    code = "PLT-DATABASE-002"
    category = "DATABASE"
    retryable = False
    http_status = 500


class DockerUnavailableError(PlatformError):
    code = "PLT-DOCKER-001"
    category = "DOCKER"
    retryable = True
    http_status = 503


class ReleaseStorageUnavailableError(PlatformError):
    code = "PLT-STORAGE-001"
    category = "STORAGE"
    retryable = True
    http_status = 503


class InternalError(PlatformError):
    code = "PLT-INTERNAL-001"
    category = "INTERNAL"
    retryable = False
    http_status = 500


class OperationNotFoundError(PlatformError):
    code = "PLT-OPERATION-001"
    category = "OPERATION"
    retryable = False
    http_status = 404


class InvalidOperationTransitionError(PlatformError):
    code = "PLT-OPERATION-002"
    category = "OPERATION"
    retryable = False
    http_status = 409


class OperationInterruptedError(PlatformError):
    code = "PLT-OPERATION-004"
    category = "OPERATION"
    retryable = True
    http_status = 500


class ApplicationLockedError(PlatformError):
    code = "PLT-LOCK-001"
    category = "LOCK"
    retryable = True
    http_status = 423


class RequestValidationFailedError(PlatformError):
    """Wraps FastAPI/Pydantic's own `RequestValidationError` (malformed
    JSON, wrong field type, or — per PL2's "Arbitrary Directory" test —
    an extra field rejected by a model's `extra="forbid"`) so a request
    validation failure still comes back through the common envelope
    (§5.1: "Every operation shall return a predictable structure")
    instead of FastAPI's own unrelated `{"detail": [...]}` shape.
    """

    code = "PLT-INPUT-003"
    category = "INPUT"
    retryable = False
    http_status = 422


class CandidateNotFoundError(PlatformError):
    """No code in §8.8 is literally "candidate not found by id" — the
    catalog's closest entry is `PLT-STORAGE-004` ("Release Package
    missing": a previously known Release Package is no longer present),
    which is semantically close enough to reuse rather than invent a new
    code outside the frozen catalog. Worth folding into the same later
    namespace-review discussion the Packager's `PKG-RUNTIME-*`/
    `PKG-RELEASE-MANIFEST-*` outliers are already flagged for in
    CURRENT.md, if a dedicated code is ever wanted.
    """

    code = "PLT-STORAGE-004"
    category = "STORAGE"
    retryable = False
    http_status = 404


# --- PL3: Release Import and Registry ---


class ReleaseManifestMissingError(PlatformError):
    code = "PLT-IMPORT-001"
    category = "IMPORT"
    retryable = False
    http_status = 422


class ReleaseManifestUnreadableError(PlatformError):
    code = "PLT-IMPORT-002"
    category = "IMPORT"
    retryable = False
    http_status = 422


class ComplianceReportMissingError(PlatformError):
    code = "PLT-IMPORT-003"
    category = "IMPORT"
    retryable = False
    http_status = 422


class ReleaseNotCompliantError(PlatformError):
    code = "PLT-IMPORT-004"
    category = "IMPORT"
    retryable = False
    http_status = 422


class ReleaseIdentityConflictError(PlatformError):
    code = "PLT-IMPORT-005"
    category = "IMPORT"
    retryable = False
    http_status = 409


class PartialImportPreventedError(PlatformError):
    code = "PLT-IMPORT-006"
    category = "IMPORT"
    retryable = True
    http_status = 500


class UnsupportedContractVersionError(PlatformError):
    code = "PLT-CONTRACT-001"
    category = "CONTRACT"
    retryable = False
    http_status = 422


class UnsupportedManifestSchemaVersionError(PlatformError):
    code = "PLT-CONTRACT-002"
    category = "CONTRACT"
    retryable = False
    http_status = 422


class ManifestSchemaInvalidError(PlatformError):
    """A manifest that parses as YAML but fails structural validation
    against `release-manifest.schema.json` — the catalog's closest fit is
    `PLT-CONTRACT-003` ("Manifest semantic rule failed"), used here for
    the broader "doesn't conform to the Contract's manifest shape" case
    since no more specific structural-validation code exists in §8.10.
    """

    code = "PLT-CONTRACT-003"
    category = "CONTRACT"
    retryable = False
    http_status = 422


class ChecksumFileMissingError(PlatformError):
    code = "PLT-INTEGRITY-001"
    category = "INTEGRITY"
    retryable = False
    http_status = 422


class ChecksumMismatchError(PlatformError):
    code = "PLT-INTEGRITY-002"
    category = "INTEGRITY"
    retryable = False
    http_status = 422


class ReleaseFingerprintMismatchError(PlatformError):
    code = "PLT-INTEGRITY-003"
    category = "INTEGRITY"
    retryable = False
    http_status = 422


class UnsupportedArchitectureError(PlatformError):
    code = "PLT-COMPATIBILITY-001"
    category = "COMPATIBILITY"
    retryable = False
    http_status = 422


class PlatformVersionTooOldError(PlatformError):
    code = "PLT-COMPATIBILITY-002"
    category = "COMPATIBILITY"
    retryable = False
    http_status = 422


class RequiredSharedServiceUnavailableError(PlatformError):
    code = "PLT-COMPATIBILITY-004"
    category = "COMPATIBILITY"
    retryable = False
    http_status = 422


# --- PL4: Application State and Action Intelligence ---


class ApplicationNotFoundError(PlatformError):
    code = "PLT-APPLICATION-001"
    category = "APPLICATION"
    retryable = False
    http_status = 404


class ReleaseNotFoundError(PlatformError):
    code = "PLT-RELEASE-001"
    category = "RELEASE"
    retryable = False
    http_status = 404


class ReleaseBelongsToAnotherApplicationError(PlatformError):
    code = "PLT-RELEASE-003"
    category = "RELEASE"
    retryable = False
    http_status = 422


# --- PL6: Fresh Installation Execution ---


class ApplicationAlreadyInstalledError(PlatformError):
    code = "PLT-APPLICATION-002"
    category = "APPLICATION"
    retryable = False
    http_status = 409


class ReleaseNotAvailableError(PlatformError):
    code = "PLT-RELEASE-002"
    category = "RELEASE"
    retryable = False
    http_status = 422


class FreshInstallUnsupportedError(PlatformError):
    code = "PLT-TRANSITION-001"
    category = "TRANSITION"
    retryable = False
    http_status = 422


class DeploymentConfigurationInvalidError(PlatformError):
    code = "PLT-INSTALL-002"
    category = "INSTALL"
    retryable = False
    http_status = 422


class PortUnavailableError(PlatformError):
    code = "PLT-CONFIG-004"
    category = "CONFIG"
    retryable = True
    http_status = 422


class InstallationScriptMissingError(PlatformError):
    code = "PLT-INSTALL-004"
    category = "INSTALL"
    retryable = False
    http_status = 422


class InstallationScriptFailedError(PlatformError):
    code = "PLT-INSTALL-005"
    category = "INSTALL"
    retryable = True
    http_status = 422


class ScriptTimedOutError(PlatformError):
    code = "PLT-SCRIPT-003"
    category = "SCRIPT"
    retryable = True
    http_status = 422


class MandatoryVerificationFailedError(PlatformError):
    code = "PLT-INSTALL-006"
    category = "INSTALL"
    retryable = True
    http_status = 422


class ActiveDeploymentCommitFailedError(PlatformError):
    """§8.15: "A technically successful host operation could not be
    committed safely to Platform state. Such a condition requires
    reconciliation." The script and verification both succeeded — the
    host really did change — but the Platform couldn't safely record it.
    Never silently claim success here; `details.reconciliation_required`
    is always `True`.
    """

    code = "PLT-INSTALL-007"
    category = "INSTALL"
    retryable = False
    http_status = 500


# --- PL7: Verification and Host Reconciliation ---


class VerificationRunNotFoundError(PlatformError):
    """No code in §8.17 (`PLT-VERIFY-001`..`008`) means "verification run
    not found" — unlike `PLT-STORAGE-004`/`PLT-APPLICATION-001` elsewhere
    in this file, there is no plausible existing code to reuse here
    (every `PLT-VERIFY-*` entry is about a check failing, not a lookup
    failing). Rather than force an ill-fitting reuse, this extends the
    category with the next number in sequence — a genuine, flagged gap in
    the frozen catalog, not a redesign. Worth folding into the same later
    namespace-review discussion as the Packager's `PKG-RUNTIME-*`
    outliers and this file's own `PLT-STORAGE-004` reuse.
    """

    code = "PLT-VERIFY-009"
    category = "VERIFY"
    retryable = False
    http_status = 404


class NoActiveDeploymentError(PlatformError):
    """A manual verification call omitted `expected_release_id` and the
    Application has no active deployment to infer it from (§4.15: "The
    Platform may infer expected_release_id from the active deployment
    when omitted"). Distinct from `ApplicationNotFoundError` — the
    Application genuinely exists, it just has nothing installed yet. No
    literal "no active deployment" code exists in §8.17's `PLT-VERIFY-*`
    range (those are all check-failure codes) or elsewhere in the
    catalog, so this extends `VERIFY` with the next sequential number —
    the same flagged-gap pattern as `VerificationRunNotFoundError` just
    above.
    """

    code = "PLT-VERIFY-010"
    category = "VERIFY"
    retryable = False
    http_status = 422


# --- PL8a: Backup and Update ---


class ApplicationNotInstalledError(PlatformError):
    """`PLT-APPLICATION-003` already exists as a *string* inside
    `application_query.py`'s own `_NOT_INSTALLED` blocking-reason
    constant (used for the `BACKUP`/`VERIFY` actions' `blocking_reasons`
    JSON), but was never wired as an actual raised exception class until
    now — `PL8a`'s standalone `create_backup()` is the first caller that
    needs to actually *raise* it (a backup with nothing installed to back
    up cannot proceed at all, not just report itself as unavailable in an
    actions list).
    """

    code = "PLT-APPLICATION-003"
    category = "APPLICATION"
    retryable = False
    http_status = 422


class UpdatePrerequisitesFailedError(PlatformError):
    """§8.16 `PLT-UPDATE-001`. The top-level "this update cannot proceed"
    signal — mirrors `prepare_update`'s own `blocking_issues` list (PL5)
    exactly: `update_application()` calls the same
    `get_available_actions()` used by planning, and if `UPDATE` isn't
    allowed, wraps its specific `blocking_reasons` (already carrying their
    own precise codes, e.g. `PLT-TRANSITION-003`) in `details` here rather
    than picking just one to surface as the top-level code.
    """

    code = "PLT-UPDATE-001"
    category = "UPDATE"
    retryable = False
    http_status = 422


class MandatoryBackupFailedError(PlatformError):
    code = "PLT-UPDATE-002"
    category = "UPDATE"
    retryable = True
    http_status = 422


class ConfigurationPreservationFailedError(PlatformError):
    """A required preserved value (most commonly a secret whose real
    plaintext only ever lived in the previous deployment's rendered
    `.env` — the Operational Registry itself never stores it, per §7.16's
    Secret-State Rule) could not be recovered from the previous
    deployment during update.
    """

    code = "PLT-UPDATE-003"
    category = "UPDATE"
    retryable = False
    http_status = 422


class UpdateScriptMissingError(PlatformError):
    code = "PLT-UPDATE-004"
    category = "UPDATE"
    retryable = False
    http_status = 422


class UpdateScriptFailedError(PlatformError):
    code = "PLT-UPDATE-005"
    category = "UPDATE"
    retryable = True
    http_status = 422


class PostUpdateVerificationFailedError(PlatformError):
    code = "PLT-UPDATE-007"
    category = "UPDATE"
    retryable = True
    http_status = 422


class UpdateRecoveryRequiredError(PlatformError):
    """§8.16 `PLT-UPDATE-008` — "The operation partially changed host
    state and cannot safely continue." The update script and
    post-update verification both succeeded — the host really is running
    the new Release — but the Registry commit itself failed, so the
    Platform cannot safely claim the new deployment is active. Same shape
    as `ActiveDeploymentCommitFailedError` (`PL6`), but the architecture
    gives update's own Registry-commit failure a dedicated code rather
    than reusing install's.
    """

    code = "PLT-UPDATE-008"
    category = "UPDATE"
    retryable = False
    http_status = 500


class BackupUnsupportedError(PlatformError):
    code = "PLT-BACKUP-001"
    category = "BACKUP"
    retryable = False
    http_status = 422


class BackupScriptMissingError(PlatformError):
    code = "PLT-BACKUP-002"
    category = "BACKUP"
    retryable = False
    http_status = 422


class BackupCreationFailedError(PlatformError):
    code = "PLT-BACKUP-003"
    category = "BACKUP"
    retryable = True
    http_status = 422


class BackupArtifactMissingError(PlatformError):
    """The backup script exited `0` but the artifact it was supposed to
    produce at the computed `storage_path` does not exist — a real
    internal-consistency check, not a speculative case: never trust a
    script's own exit code alone to mean the artifact is genuinely there.
    """

    code = "PLT-BACKUP-004"
    category = "BACKUP"
    retryable = False
    http_status = 500


class BackupNotFoundError(PlatformError):
    """No code in §8.20 (`PLT-BACKUP-001`..`007`) fits "no backup exists
    with this id" — every existing `PLT-BACKUP-*` entry is about a
    creation/verification/ownership failure, not a lookup failure. Same
    flagged-gap pattern as `VerificationRunNotFoundError` (`PL7`,
    `PLT-VERIFY-009`) and `NoActiveDeploymentError` (`PL7`,
    `PLT-VERIFY-010`): extends the category with the next sequential
    number rather than forcing an ill-fitting reuse.
    """

    code = "PLT-BACKUP-008"
    category = "BACKUP"
    retryable = False
    http_status = 404
