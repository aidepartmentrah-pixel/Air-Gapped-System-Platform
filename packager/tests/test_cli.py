import json

from click.testing import CliRunner

from rah_packager.cli import main


def _invoke_json(runner: CliRunner, args: list[str], env: dict | None = None) -> dict:
    result = runner.invoke(main, args, env=env)
    return result, json.loads(result.output)


# --- Structured Result Test ---


def test_version_command_returns_valid_json_envelope():
    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["version"])
    assert result.exit_code == 0
    assert envelope["ok"] is True
    assert envelope["command"] == "version"
    assert "packager_version" in envelope["result"]


def test_health_command_returns_valid_json_envelope():
    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["health"])
    assert result.exit_code == 0
    assert envelope["ok"] is True
    assert envelope["command"] == "health"
    assert envelope["result"]["docker"]["reachable"] is True


def test_eager_version_flag_still_works():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "rah" in result.output


# --- Failure Test (CLI level: deterministic error, not a crash) ---


def test_health_command_reports_structured_error_when_docker_unavailable(monkeypatch):
    def fail_from_env():
        from docker.errors import DockerException

        raise DockerException("no such host")

    monkeypatch.setattr("rah_packager.docker_client.docker.from_env", fail_from_env)

    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["health"])

    assert result.exit_code == 1
    # sys.exit(1) after printing the envelope raises SystemExit by design —
    # CliRunner reports that as result.exception. What must NOT happen is an
    # unhandled crash from anywhere other than that deliberate exit call, and
    # the JSON envelope must still have printed correctly beforehand (already
    # proven by _invoke_json's json.loads succeeding above).
    assert isinstance(result.exception, SystemExit), "unexpected crash, not a controlled exit"
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PKG-RUNTIME-DOCKER-UNAVAILABLE"
