import pytest

from rah_packager.config import Config
from rah_packager.errors import ClaudeAuthenticationError, DockerUnavailableError
from rah_packager.health import _check_output_path, _check_repo_path, run_health_check


# --- Mounted Repository Test ---


def test_repo_path_readable(tmp_path):
    (tmp_path / "some_file.txt").write_text("hello")
    result = _check_repo_path(str(tmp_path))
    assert result["readable"] is True
    assert result["entry_count"] == 1


def test_repo_path_missing_reported_not_crashed(tmp_path):
    missing = tmp_path / "does-not-exist"
    result = _check_repo_path(str(missing))
    assert result["readable"] is False


# --- Output Test ---


def test_output_path_round_trip(tmp_path):
    result = _check_output_path(str(tmp_path))
    assert result["writable"] is True
    # the marker file must not be left behind
    assert not (tmp_path / ".rah-health-check").exists()


def test_output_path_created_if_missing(tmp_path):
    target = tmp_path / "nested" / "output"
    result = _check_output_path(str(target))
    assert result["writable"] is True


# --- Docker Connectivity Test (real Docker Engine, no mocking) ---


def test_health_check_reaches_real_docker_engine():
    config = Config(repo_path=None, output_path=None, log_level="INFO", anthropic_api_key=None)
    report = run_health_check(config)
    assert report["docker"]["reachable"] is True
    assert report["docker"]["server_version"]


def test_health_check_includes_repo_and_output_when_configured(tmp_path):
    config = Config(
        repo_path=str(tmp_path),
        output_path=str(tmp_path),
        log_level="INFO",
        anthropic_api_key=None,
    )
    report = run_health_check(config)
    assert "mounted_repository" in report
    assert "output_directory" in report


# --- Claude Credentials Check ---


def test_health_reports_claude_not_configured():
    config = Config(repo_path=None, output_path=None, log_level="INFO", anthropic_api_key=None)
    report = run_health_check(config)
    assert report["claude"] == {"configured": False, "source": None, "valid": None, "error": None}


def test_health_reports_claude_valid(monkeypatch):
    monkeypatch.setattr("rah_packager.health.validate_api_key", lambda api_key: None)
    config = Config(
        repo_path=None,
        output_path=None,
        log_level="INFO",
        anthropic_api_key="sk-ant-fake",
        anthropic_api_key_source="env",
    )
    report = run_health_check(config)
    assert report["claude"] == {"configured": True, "source": "env", "valid": True, "error": None}


def test_health_reports_claude_invalid(monkeypatch):
    def _fail(api_key):
        raise ClaudeAuthenticationError("bad key")

    monkeypatch.setattr("rah_packager.health.validate_api_key", _fail)
    config = Config(
        repo_path=None,
        output_path=None,
        log_level="INFO",
        anthropic_api_key="sk-ant-fake",
        anthropic_api_key_source="file",
    )
    report = run_health_check(config)
    assert report["claude"]["configured"] is True
    assert report["claude"]["valid"] is False
    assert report["claude"]["error"]["code"] == "PKG-CLAUDE-AUTHENTICATION-FAILED"


# --- Failure Test ---


def test_docker_unavailable_raises_packager_error(monkeypatch):
    def fail_from_env():
        from docker.errors import DockerException

        raise DockerException("no such host")

    monkeypatch.setattr("rah_packager.docker_client.docker.from_env", fail_from_env)

    config = Config(repo_path=None, output_path=None, log_level="INFO", anthropic_api_key=None)
    with pytest.raises(DockerUnavailableError) as exc_info:
        run_health_check(config)

    assert exc_info.value.code == "PKG-DOCKER-UNAVAILABLE"
