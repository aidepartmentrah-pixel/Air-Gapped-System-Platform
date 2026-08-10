from pathlib import Path

from rah_packager.application_resources_inspection import inspect_application_resources

FIXTURES = Path(__file__).parent / "fixtures" / "projects"


def test_valid_simple_app_discovers_every_category():
    result = inspect_application_resources(FIXTURES / "valid-simple-app")

    assert result["scripts"] == [
        "scripts/install_offline.sh",
        "scripts/verify_deployment.sh",
    ]
    assert result["migration_directories"] == ["backend/migrations"]
    assert result["configuration_templates"] == [".env.example", "backend/.env.example"]
    assert result["environment_variables"] == [
        "API_TOKEN",
        "DATABASE_URL",
        "PORT",
        "SECRET_KEY",
    ]
    assert result["documentation"] == ["README.md", "documentation/INSTALL.md"]
    assert result["verification_candidates"] == ["scripts/verify_deployment.sh"]


# --- Missing is not an error; empty repo reports empty, not a crash ---


def test_empty_repo_reports_all_empty_lists(tmp_path):
    (tmp_path / "unrelated.txt").write_text("nothing relevant here")

    result = inspect_application_resources(tmp_path)

    assert result == {
        "scripts": [],
        "migration_directories": [],
        "configuration_templates": [],
        "environment_variables": [],
        "documentation": [],
        "verification_candidates": [],
    }


# --- Noise directories are pruned, same as Docker inspection ---


def test_ignores_node_modules_and_venv(tmp_path):
    (tmp_path / "node_modules" / "scripts").mkdir(parents=True)
    (tmp_path / "node_modules" / "scripts" / "sneaky.sh").write_text("echo sneaky")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "real.sh").write_text("echo real")

    result = inspect_application_resources(tmp_path)

    assert result["scripts"] == ["scripts/real.sh"]


# --- Comments and blank lines in config templates are skipped ---


def test_env_var_extraction_skips_comments_and_blank_lines(tmp_path):
    (tmp_path / ".env.example").write_text(
        "\n# comment\nFOO=bar\n\n  # indented comment\nBAZ=qux\n"
    )

    result = inspect_application_resources(tmp_path)

    assert result["environment_variables"] == ["BAZ", "FOO"]


# --- Categories are not mutually exclusive ---


def test_file_can_appear_in_both_documentation_and_verification_candidates(tmp_path):
    (tmp_path / "VALIDATION_CHECKLIST.md").write_text("# checklist")

    result = inspect_application_resources(tmp_path)

    assert "VALIDATION_CHECKLIST.md" in result["documentation"]
    assert "VALIDATION_CHECKLIST.md" in result["verification_candidates"]
