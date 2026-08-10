from rah_platform import health
from rah_platform.config import Config


# --- Liveness Test ---


def test_liveness_reports_up():
    assert health.liveness() == {"status": "UP"}


# --- Readiness Test (all real dependencies healthy) ---


def test_readiness_reports_ready_when_all_dependencies_healthy(postgres_url, tmp_path):
    config = Config(database_url=postgres_url, release_storage_path=str(tmp_path), log_level="INFO")
    result = health.readiness(config)
    assert result["status"] == "READY"
    assert result["checks"] == {"database": "PASS", "docker": "PASS", "release_storage": "PASS"}
    assert "failures" not in result


# --- Docker Failure ---


def test_readiness_reports_not_ready_when_docker_unavailable(monkeypatch, postgres_url, tmp_path):
    def fail_from_env():
        from docker.errors import DockerException

        raise DockerException("no such host")

    monkeypatch.setattr("rah_platform.docker_client.docker.from_env", fail_from_env)

    config = Config(database_url=postgres_url, release_storage_path=str(tmp_path), log_level="INFO")
    result = health.readiness(config)
    assert result["status"] == "NOT_READY"
    assert result["checks"]["docker"] == "FAIL"
    assert result["failures"]["docker"]["code"] == "PLT-DOCKER-001"
    # unrelated dependencies still evaluated independently
    assert result["checks"]["database"] == "PASS"


# --- PostgreSQL Failure ---


def test_readiness_reports_not_ready_when_database_unavailable(tmp_path):
    config = Config(
        database_url="postgresql+psycopg://nobody:nothing@127.0.0.1:1/does_not_exist",
        release_storage_path=str(tmp_path),
        log_level="INFO",
    )
    result = health.readiness(config)
    assert result["status"] == "NOT_READY"
    assert result["checks"]["database"] == "FAIL"
    assert result["failures"]["database"]["code"] == "PLT-DATABASE-003"


# --- Release Storage Failure ---


def test_readiness_reports_not_ready_when_release_storage_missing(postgres_url, tmp_path):
    missing = tmp_path / "does-not-exist"
    config = Config(database_url=postgres_url, release_storage_path=str(missing), log_level="INFO")
    result = health.readiness(config)
    assert result["status"] == "NOT_READY"
    assert result["checks"]["release_storage"] == "FAIL"
    assert result["failures"]["release_storage"]["code"] == "PLT-STORAGE-001"
