from rah_platform.config import Config


def test_from_env_defaults(monkeypatch):
    monkeypatch.delenv("RAH_DATABASE_URL", raising=False)
    monkeypatch.delenv("RAH_RELEASE_STORAGE_PATH", raising=False)
    monkeypatch.delenv("RAH_LOG_LEVEL", raising=False)
    config = Config.from_env()
    assert config.database_url.startswith("postgresql+psycopg://")
    assert config.release_storage_path == "/data/releases"
    assert config.log_level == "INFO"


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("RAH_DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    monkeypatch.setenv("RAH_RELEASE_STORAGE_PATH", "/custom/releases")
    monkeypatch.setenv("RAH_LOG_LEVEL", "DEBUG")
    config = Config.from_env()
    assert config.database_url == "postgresql+psycopg://u:p@host:5432/db"
    assert config.release_storage_path == "/custom/releases"
    assert config.log_level == "DEBUG"
