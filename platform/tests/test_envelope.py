import uuid

from rah_platform.envelope import error_envelope, success_envelope
from rah_platform.errors import InternalError


def test_success_envelope_shape():
    env = success_envelope({"status": "UP"})
    assert env["success"] is True
    assert env["data"] == {"status": "UP"}
    assert env["warnings"] == []
    assert env["error"] is None
    uuid.UUID(env["request_id"])  # does not raise
    assert env["timestamp"]


def test_error_envelope_shape():
    env = error_envelope(InternalError("boom"))
    assert env["success"] is False
    assert env["data"] is None
    assert env["error"]["code"] == "PLT-INTERNAL-001"
    assert env["error"]["request_id"] == env["request_id"]
