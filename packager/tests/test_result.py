import json

from rah_packager.errors import PackagerError
from rah_packager.result import failure, ok, render


def test_ok_envelope_shape():
    envelope = ok("health", {"a": 1})
    assert envelope == {"ok": True, "command": "health", "result": {"a": 1}, "error": None}


def test_failure_envelope_shape():
    err = PackagerError(code="PKG-TEST-001", message="something broke")
    envelope = failure("health", err)
    assert envelope == {
        "ok": False,
        "command": "health",
        "result": None,
        "error": {"code": "PKG-TEST-001", "message": "something broke"},
    }


def test_render_produces_valid_json():
    envelope = ok("version", {"packager_version": "0.0.1"})
    rendered = render(envelope)
    assert json.loads(rendered) == envelope
