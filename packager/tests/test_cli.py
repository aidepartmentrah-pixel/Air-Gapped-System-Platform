import json
import subprocess
from pathlib import Path

import docker
from click.testing import CliRunner

from rah_packager.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "projects"


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


# --- `rah validate-answers` (P3 subtask 3, no Claude API call) ---


def test_validate_answers_reports_missing_file(tmp_path):
    _git_init_with_commit(tmp_path)

    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["validate-answers", "--project", str(tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "unexpected crash, not a controlled exit"
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PKG-ENGINEERING-ANSWERS-NOT-FOUND"


def test_validate_answers_accepts_a_valid_matching_file(tmp_path):
    import json as _json

    from rah_packager.engineering_answers import compute_inspection_fingerprint
    from rah_packager.inspection import inspect_project

    _git_init_with_commit(tmp_path)
    inspection_result = inspect_project(tmp_path)

    answers = {
        "schema_version": "1.0",
        "based_on": {
            "git_commit": inspection_result["git"]["commit"],
            "inspection_fingerprint": compute_inspection_fingerprint(inspection_result),
        },
        "application": {"description": "A test application."},
        "compatibility": {"minimum_rah_oip_version": "1.0", "supported_architectures": ["amd64"]},
        "deployment": {"entrypoints": {}, "supported_operations": {"fresh_install": True}},
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
        # README.md is the only doc file `_git_init_with_commit` created —
        # pointing at anything else here would trip the consistency check.
        "documentation": {
            "release_notes": "README.md",
            "installation": "README.md",
            "update": "README.md",
            "recovery": "README.md",
            "known_issues": "README.md",
        },
    }
    answers_dir = tmp_path / ".rah"
    answers_dir.mkdir()
    (answers_dir / "engineering-answers.json").write_text(_json.dumps(answers))

    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["validate-answers", "--project", str(tmp_path)])

    assert result.exit_code == 0
    assert envelope["ok"] is True
    assert envelope["result"]["valid"] is True


# --- `rah prepare-answers` (P3 subtask 2, real Claude API call — mocked here) ---


def test_prepare_answers_reports_missing_api_key(tmp_path, monkeypatch):
    _git_init_with_commit(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("RAH_CREDENTIALS_FILE", str(tmp_path / "nonexistent-credentials.env"))

    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["prepare-answers", "--project", str(tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "unexpected crash, not a controlled exit"
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PKG-CLAUDE-API-KEY-MISSING"


def test_prepare_answers_command_writes_valid_answers(tmp_path, monkeypatch):
    from rah_packager import prepare_answers as prepare_answers_module

    _git_init_with_commit(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")

    claude_answer = {
        "application": {"description": "A test application."},
        "compatibility": {"minimum_rah_oip_version": "1.0", "supported_architectures": ["amd64"]},
        "deployment": {"entrypoints": {}, "supported_operations": {"fresh_install": True}},
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
        # README.md is the only doc file `_git_init_with_commit` created.
        "documentation": {
            "release_notes": "README.md",
            "installation": "README.md",
            "update": "README.md",
            "recovery": "README.md",
            "known_issues": "README.md",
        },
    }

    class _FakeContentBlock:
        type = "tool_use"
        input = claude_answer

    class _FakeResponse:
        stop_reason = "tool_use"
        content = [_FakeContentBlock()]

    class _FakeMessages:
        def create(self, **kwargs):
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, api_key):
            self.messages = _FakeMessages()

    monkeypatch.setattr(prepare_answers_module.anthropic, "Anthropic", _FakeClient)

    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["prepare-answers", "--project", str(tmp_path)])

    assert result.exit_code == 0
    assert envelope["ok"] is True
    assert envelope["result"]["schema_valid"] is True
    assert (tmp_path / ".rah" / "engineering-answers.json").exists()


# --- `rah plan` (P4, no Claude API call) ---


def test_plan_reports_project_not_initialized(tmp_path):
    _git_init_with_commit(tmp_path)

    runner = CliRunner()
    result, envelope = _invoke_json(runner, ["plan", "--project", str(tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "unexpected crash, not a controlled exit"
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PKG-PLAN-PROJECT-NOT-INITIALIZED"


def test_plan_command_returns_valid_json_envelope(tmp_path):
    import json as _json

    from rah_packager.engineering_answers import compute_inspection_fingerprint
    from rah_packager.inspection import inspect_project

    _git_init_with_commit(tmp_path)
    runner = CliRunner()
    runner.invoke(
        main, ["init", "--project", str(tmp_path), "--name", "HCAT", "--slug", "hcat"]
    )

    inspection_result = inspect_project(tmp_path)
    answers = {
        "schema_version": "1.0",
        "based_on": {
            "git_commit": inspection_result["git"]["commit"],
            "inspection_fingerprint": compute_inspection_fingerprint(inspection_result),
        },
        "application": {"description": "A test application."},
        "compatibility": {"minimum_rah_oip_version": "1.0", "supported_architectures": ["amd64"]},
        "deployment": {"entrypoints": {}, "supported_operations": {"fresh_install": True}},
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
            "release_notes": "README.md",
            "installation": "README.md",
            "update": "README.md",
            "recovery": "README.md",
            "known_issues": "README.md",
        },
    }
    answers_dir = tmp_path / ".rah"
    (answers_dir / "engineering-answers.json").write_text(_json.dumps(answers))

    result, envelope = _invoke_json(runner, ["plan", "--project", str(tmp_path)])

    assert result.exit_code == 0
    assert envelope["ok"] is True
    assert envelope["result"]["proposed_version"] == "1.0.0"
    assert envelope["result"]["current_release"] is None
    assert envelope["result"]["may_proceed"] is True


# --- `rah build` (P5, real Docker build against the real Engine) ---


def test_build_command_returns_valid_json_envelope(tmp_path):
    client = docker.from_env()
    slug = "pytest-p5-cli"
    try:
        runner = CliRunner()
        result, envelope = _invoke_json(
            runner,
            [
                "build",
                "--project",
                str(FIXTURES / "trivial-one-container"),
                "--output",
                str(tmp_path / "workspace"),
                "--slug",
                slug,
                "--version",
                "0.0.1",
            ],
        )

        assert result.exit_code == 0
        assert envelope["ok"] is True
        assert envelope["command"] == "build"
        assert envelope["result"]["images"][0]["built"] is True
        assert (tmp_path / "workspace" / "docker-images").is_dir()
    finally:
        try:
            client.images.remove(f"rah-{slug}-app:0.0.1", force=True)
        except docker.errors.ImageNotFound:
            pass


def test_build_command_reports_structured_error_for_broken_dockerfile(tmp_path):
    runner = CliRunner()
    result, envelope = _invoke_json(
        runner,
        [
            "build",
            "--project",
            str(FIXTURES / "broken-dockerfile"),
            "--output",
            str(tmp_path / "workspace"),
            "--slug",
            "pytest-p5-cli",
            "--version",
            "0.0.1",
        ],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "unexpected crash, not a controlled exit"
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "PKG-DOCKER-BUILD-FAILED"
