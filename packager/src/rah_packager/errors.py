"""Packager operational errors.

The full PKG-* operational error-code namespace is a deliberately deferred
design task (see docs/development/CURRENT.md, "Future Design Tasks") — do
not extend this module into a full taxonomy without that discussion
happening first. This file defines only the error(s) P0 actually needs.
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
