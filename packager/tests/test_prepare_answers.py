import json
import subprocess

import anthropic
import httpx
import pytest

from rah_packager.errors import (
    ClaudeAPIError,
    ClaudeAPIKeyMissingError,
    ClaudeAuthenticationError,
    ClaudeConnectionError,
    ClaudeRateLimitedError,
    ClaudeRefusalError,
    EngineeringAnswersSchemaError,
)
from rah_packager.inspection import inspect_project
from rah_packager.prepare_answers import (
    build_context_bundle,
    build_suggestions,
    prepare_answers,
)
from rah_packager.validate_answers import default_answers_path, validate_answers


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _setup_repo(tmp_path) -> dict:
    """Filenames chosen to match the real, evidence-checked keyword patterns
    `build_suggestions` looks for (see HCopilot's real release/ layout).
    """
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "install_offline.sh").write_text("#!/bin/sh\necho install\n")
    (tmp_path / "scripts" / "update_offline.sh").write_text("#!/bin/sh\necho update\n")
    (tmp_path / "scripts" / "verify_installation.sh").write_text("#!/bin/sh\necho verify\n")
    (tmp_path / "scripts" / "backup_database.sh").write_text("#!/bin/sh\necho backup\n")
    (tmp_path / "scripts" / "restore_database.sh").write_text("#!/bin/sh\necho restore\n")
    (tmp_path / "RELEASE_NOTES.md").write_text("# Release Notes")
    (tmp_path / "INSTALL_OFFLINE.md").write_text("# Install")
    (tmp_path / "UPDATE_OFFLINE.md").write_text("# Update")
    (tmp_path / "BACKUP_RESTORE.md").write_text("# Backup and Restore")
    (tmp_path / "TROUBLESHOOTING.md").write_text("# Known Issues")
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  db:\n    image: mcr.microsoft.com/mssql/server:2022-latest\n"
    )

    _git(tmp_path, "init", "--quiet", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init")

    return inspect_project(tmp_path)


# --- build_suggestions: three-tier pre-fill, checked against real evidence ---


def test_build_suggestions_guesses_entrypoints_and_verification(tmp_path):
    inspection_result = _setup_repo(tmp_path)

    suggestions = build_suggestions(inspection_result)

    assert suggestions["deployment"]["entrypoints"] == {
        "install": "scripts/install_offline.sh",
        "update": "scripts/update_offline.sh",
        "verify": "scripts/verify_installation.sh",
        "backup": "scripts/backup_database.sh",
        "restore": "scripts/restore_database.sh",
    }
    assert suggestions["verification"]["entrypoint"] == "scripts/verify_installation.sh"


def test_build_suggestions_guesses_documentation(tmp_path):
    inspection_result = _setup_repo(tmp_path)

    suggestions = build_suggestions(inspection_result)

    assert suggestions["documentation"] == {
        "release_notes": "RELEASE_NOTES.md",
        "installation": "INSTALL_OFFLINE.md",
        "update": "UPDATE_OFFLINE.md",
        "recovery": "BACKUP_RESTORE.md",
        "known_issues": "TROUBLESHOOTING.md",
    }


def test_build_suggestions_guesses_database_platform_from_image(tmp_path):
    inspection_result = _setup_repo(tmp_path)

    suggestions = build_suggestions(inspection_result)

    assert suggestions["database"]["platform"] == "sqlserver"


def test_build_suggestions_always_includes_contract_defaults(tmp_path):
    (tmp_path / "README.md").write_text("hello")
    _git(tmp_path, "init", "--quiet", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init")
    inspection_result = inspect_project(tmp_path)

    suggestions = build_suggestions(inspection_result)

    assert suggestions["offline_requirements"] == {
        "public_internet_required": False,
        "public_registry_required": False,
        "public_cdn_required": False,
        "online_model_registry_required": False,
    }
    assert suggestions["models"] == {"required": False}
    assert suggestions["client"] == {"preparation_required": False, "https_required": False}
    # No scripts/docs discovered — no entrypoint or documentation guesses.
    assert "deployment" not in suggestions
    assert "documentation" not in suggestions
    assert "database" not in suggestions


def test_build_context_bundle_includes_file_contents_and_suggestions(tmp_path):
    inspection_result = _setup_repo(tmp_path)
    suggestions = build_suggestions(inspection_result)

    context = build_context_bundle(tmp_path, inspection_result, suggestions)

    assert "scripts/install_offline.sh" in context
    assert "echo install" in context
    assert '"install": "scripts/install_offline.sh"' in context


# --- prepare_answers: no API key ---


def test_prepare_answers_requires_api_key(tmp_path):
    _setup_repo(tmp_path)

    with pytest.raises(ClaudeAPIKeyMissingError) as exc_info:
        prepare_answers(tmp_path, None)
    assert exc_info.value.code == "PKG-CLAUDE-API-KEY-MISSING"


# --- prepare_answers: real Claude call, mocked at the SDK boundary ---


def _valid_claude_answer() -> dict:
    return {
        "application": {"description": "A test application."},
        "compatibility": {"minimum_rah_oip_version": "1.0", "supported_architectures": ["amd64"]},
        "deployment": {
            "entrypoints": {"install": "scripts/install_offline.sh"},
            "supported_operations": {"fresh_install": True},
        },
        "configuration": {"inputs": []},
        "database": {"required": False},
        "persistent_state": {"preserve_during_update": []},
        "offline_requirements": {
            "public_internet_required": False,
            "public_registry_required": False,
            "public_cdn_required": False,
            "online_model_registry_required": False,
        },
        "models": {"required": False},
        "client": {"preparation_required": False, "https_required": False},
        "verification": {"required_checks": []},
        "documentation": {
            "release_notes": "RELEASE_NOTES.md",
            "installation": "INSTALL_OFFLINE.md",
            "update": "UPDATE_OFFLINE.md",
            "recovery": "BACKUP_RESTORE.md",
            "known_issues": "TROUBLESHOOTING.md",
        },
    }


class _FakeContentBlock:
    def __init__(self, type_, input_=None):
        self.type = type_
        self.input = input_


class _FakeResponse:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _FakeMessages:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._exc is not None:
            raise self._exc
        return self._response


class _FakeClient:
    def __init__(self, response=None, exc=None):
        self.messages = _FakeMessages(response, exc)


def _patch_client(monkeypatch, response=None, exc=None):
    created: list[_FakeClient] = []
    monkeypatch.setattr(
        "rah_packager.prepare_answers.anthropic.Anthropic",
        lambda api_key: created.append(_FakeClient(response, exc)) or created[-1],
    )
    return created


def test_prepare_answers_writes_valid_file_that_passes_validate_answers(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    response = _FakeResponse(
        "tool_use", [_FakeContentBlock("tool_use", _valid_claude_answer())]
    )
    _patch_client(monkeypatch, response=response)

    result = prepare_answers(tmp_path, "sk-ant-fake")

    assert result["schema_valid"] is True
    answers_path = default_answers_path(tmp_path)
    assert str(answers_path) == result["answers_path"]
    on_disk = json.loads(answers_path.read_text())
    assert on_disk["based_on"] == result["based_on"]
    assert on_disk["schema_version"] == "1.0"

    assert validate_answers(tmp_path) == {
        "answers_path": str(answers_path),
        "valid": True,
        "stale": False,
    }


def test_prepare_answers_forces_the_submit_tool(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    response = _FakeResponse(
        "tool_use", [_FakeContentBlock("tool_use", _valid_claude_answer())]
    )
    created = _patch_client(monkeypatch, response=response)

    prepare_answers(tmp_path, "sk-ant-fake")

    kwargs = created[0].messages.last_kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "submit_engineering_answers"}
    assert kwargs["tools"][0]["name"] == "submit_engineering_answers"
    assert kwargs["model"] == "claude-opus-5"


def test_prepare_answers_overwrites_unconditionally(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    response = _FakeResponse(
        "tool_use", [_FakeContentBlock("tool_use", _valid_claude_answer())]
    )
    _patch_client(monkeypatch, response=response)

    prepare_answers(tmp_path, "sk-ant-fake")
    answers_path = default_answers_path(tmp_path)
    answers_path.write_text('{"not": "valid engineering answers"}')

    # A second run must not refuse just because the file already exists —
    # it should overwrite it with a fresh, valid answer.
    result = prepare_answers(tmp_path, "sk-ant-fake")
    assert result["schema_valid"] is True
    on_disk = json.loads(answers_path.read_text())
    assert on_disk["schema_version"] == "1.0"


def test_prepare_answers_deterministic_fields_win_over_claude_output(tmp_path, monkeypatch):
    tampered = _valid_claude_answer()
    tampered["schema_version"] = "9.9"
    tampered["based_on"] = {"git_commit": "0" * 40, "inspection_fingerprint": "0" * 64}
    response = _FakeResponse("tool_use", [_FakeContentBlock("tool_use", tampered)])
    inspection_result = _setup_repo(tmp_path)
    _patch_client(monkeypatch, response=response)

    result = prepare_answers(tmp_path, "sk-ant-fake")

    assert result["based_on"]["git_commit"] == inspection_result["git"]["commit"]
    assert result["based_on"]["git_commit"] != "0" * 40


def test_prepare_answers_handles_refusal(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    response = _FakeResponse("refusal", [])
    _patch_client(monkeypatch, response=response)

    with pytest.raises(ClaudeRefusalError) as exc_info:
        prepare_answers(tmp_path, "sk-ant-fake")
    assert exc_info.value.code == "PKG-CLAUDE-REFUSED"


def test_prepare_answers_rejects_claude_output_that_fails_schema(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    broken = _valid_claude_answer()
    del broken["database"]
    response = _FakeResponse("tool_use", [_FakeContentBlock("tool_use", broken)])
    _patch_client(monkeypatch, response=response)

    with pytest.raises(EngineeringAnswersSchemaError):
        prepare_answers(tmp_path, "sk-ant-fake")


# --- prepare_answers: SDK error mapping, same pattern as test_claude_client.py ---


def _request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _http_response(status_code):
    return httpx.Response(status_code, request=_request())


def test_authentication_error_mapped(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    exc = anthropic.AuthenticationError("invalid x-api-key", response=_http_response(401), body=None)
    _patch_client(monkeypatch, exc=exc)

    with pytest.raises(ClaudeAuthenticationError) as exc_info:
        prepare_answers(tmp_path, "sk-ant-fake")
    assert exc_info.value.code == "PKG-CLAUDE-AUTHENTICATION-FAILED"


def test_rate_limit_error_mapped(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    exc = anthropic.RateLimitError("rate limited", response=_http_response(429), body=None)
    _patch_client(monkeypatch, exc=exc)

    with pytest.raises(ClaudeRateLimitedError) as exc_info:
        prepare_answers(tmp_path, "sk-ant-fake")
    assert exc_info.value.code == "PKG-CLAUDE-RATE-LIMITED"


def test_connection_error_mapped(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    exc = anthropic.APIConnectionError(request=_request())
    _patch_client(monkeypatch, exc=exc)

    with pytest.raises(ClaudeConnectionError) as exc_info:
        prepare_answers(tmp_path, "sk-ant-fake")
    assert exc_info.value.code == "PKG-CLAUDE-CONNECTION-FAILED"


def test_generic_api_status_error_mapped(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    exc = anthropic.APIStatusError("server error", response=_http_response(500), body=None)
    _patch_client(monkeypatch, exc=exc)

    with pytest.raises(ClaudeAPIError) as exc_info:
        prepare_answers(tmp_path, "sk-ant-fake")
    assert exc_info.value.code == "PKG-CLAUDE-API-ERROR"
