from rah_packager.config import Config


def test_env_var_takes_precedence_over_credentials_file(tmp_path, monkeypatch):
    creds_file = tmp_path / "credentials.env"
    creds_file.write_text("ANTHROPIC_API_KEY=from-file\n")
    monkeypatch.setenv("RAH_CREDENTIALS_FILE", str(creds_file))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")

    config = Config.from_env()

    assert config.anthropic_api_key == "from-env"
    assert config.anthropic_api_key_source == "env"


def test_falls_back_to_credentials_file_when_env_unset(tmp_path, monkeypatch):
    creds_file = tmp_path / "credentials.env"
    creds_file.write_text("ANTHROPIC_API_KEY=from-file\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("RAH_CREDENTIALS_FILE", str(creds_file))

    config = Config.from_env()

    assert config.anthropic_api_key == "from-file"
    assert config.anthropic_api_key_source == "file"


def test_neither_env_nor_file_is_none(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("RAH_CREDENTIALS_FILE", str(tmp_path / "does-not-exist.env"))

    config = Config.from_env()

    assert config.anthropic_api_key is None
    assert config.anthropic_api_key_source is None


def test_credentials_file_ignores_comments_and_blank_lines(tmp_path, monkeypatch):
    creds_file = tmp_path / "credentials.env"
    creds_file.write_text("\n# a comment\nANTHROPIC_API_KEY=real-value\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("RAH_CREDENTIALS_FILE", str(creds_file))

    config = Config.from_env()

    assert config.anthropic_api_key == "real-value"


def test_credentials_file_without_the_key_is_none(tmp_path, monkeypatch):
    creds_file = tmp_path / "credentials.env"
    creds_file.write_text("SOME_OTHER_VAR=x\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("RAH_CREDENTIALS_FILE", str(creds_file))

    config = Config.from_env()

    assert config.anthropic_api_key is None
    assert config.anthropic_api_key_source is None


def test_credentials_file_with_utf8_bom_still_parses(tmp_path, monkeypatch):
    # PowerShell's `Out-File -Encoding utf8` writes a BOM by default —
    # real-world regression, not a hypothetical (found live: PKG-CLAUDE
    # health check reported "configured: false" against a real key because
    # of this).
    creds_file = tmp_path / "credentials.env"
    creds_file.write_bytes(b"\xef\xbb\xbfANTHROPIC_API_KEY=from-bom-file")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("RAH_CREDENTIALS_FILE", str(creds_file))

    config = Config.from_env()

    assert config.anthropic_api_key == "from-bom-file"
    assert config.anthropic_api_key_source == "file"
