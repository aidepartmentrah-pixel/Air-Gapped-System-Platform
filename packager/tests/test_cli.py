import json
import subprocess

from click.testing import CliRunner

from rah_packager.cli import main


def _invoke_json(runner: CliRunner, args: list[str], env: dict | None = None) -> dict:
    result = runner.invoke(main, args, env=env)
    return result, json.loads(result.output)


def _git_init_with_commit(path):
    """A bare `git init` has no commits, so `HEAD` doesn't resolve — several
    `inspect` tests need a real, committed repo, not just a `.git` directory.
    """
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=path, check=True)
    (path / "README.md").write_text("hello")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "init"], cwd=path, check=True)


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


# --- `rah init` (P1) ---


def test_init_command_returns_valid_json_envelope(tmp_path):
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)

    runner = CliRunner()
    result, envelope = _invoke_json(
        runner,
        ["init", "--project", str(tmp_path), "--name", "HCAT", "--slug", "hcat"],
    )

    assert result.exit_code == 0
    assert envelope["ok"] is True
    assert envelope["command"] == "init"
    assert envelope["result"]["application"] == {"name": "HCAT", "slug": "hcat"}
    assert (tmp_path / ".rah" / "project-state.json").exists()


def test_init_command_reports_structured_error_for_non_git_repository(tmp_path):
    runner = CliRunner()
    result, envelope = _invoke_json(
        runner,
        ["init", "--project", str(tmp_path), "--name", "HCAT", "--slug", "hcat"],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "unexpected crash, not a controlled exit"
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PKG-GIT-NOT-A-REPOSITORY"


# --- `rah inspect` (P2, Git facts so far) ---


def test_inspect_command_returns_valid_json_envelope(tmp_path):
    _git_init_with_commit(tmp_path)

    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["inspect", "--project", str(tmp_path)])

    assert result.exit_code == 0
    assert envelope["ok"] is True
    assert envelope["command"] == "inspect"
    assert envelope["result"]["git"]["branch"] == "main"
    assert envelope["result"]["git"]["state"] == "clean"


def test_inspect_command_reports_structured_error_for_non_git_repository(tmp_path):
    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["inspect", "--project", str(tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "unexpected crash, not a controlled exit"
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PKG-GIT-NOT-A-REPOSITORY"


def test_inspect_reports_packager_state_none_before_init(tmp_path):
    _git_init_with_commit(tmp_path)

    runner = CliRunner()
    _, envelope = _invoke_json(runner, ["inspect", "--project", str(tmp_path)])

    assert envelope["result"]["packager_state"] is None


def test_init_then_inspect_reports_packager_state(tmp_path):
    _git_init_with_commit(tmp_path)

    runner = CliRunner()
    runner.invoke(
        main, ["init", "--project", str(tmp_path), "--name", "HCAT", "--slug", "hcat"]
    )
    _, envelope = _invoke_json(runner, ["inspect", "--project", str(tmp_path)])

    assert envelope["result"]["packager_state"] == {
        "application": {"name": "HCAT", "slug": "hcat"},
        "current_release": None,
        "next_version": "1.0.0",
        "release_history": [],
    }
