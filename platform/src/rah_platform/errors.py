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
