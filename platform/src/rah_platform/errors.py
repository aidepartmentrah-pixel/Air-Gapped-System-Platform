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
