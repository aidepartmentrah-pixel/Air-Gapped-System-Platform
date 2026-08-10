from fastapi.testclient import TestClient

from rah_platform.app import create_app
from rah_platform.config import Config


def _client(config: Config) -> TestClient:
    return TestClient(create_app(config))


def test_liveness_endpoint_envelope(postgres_url, tmp_path):
    config = Config(database_url=postgres_url, release_storage_path=str(tmp_path), log_level="INFO")
    response = _client(config).get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"status": "UP"}
    assert body["error"] is None


def test_readiness_endpoint_200_when_ready(postgres_url, tmp_path):
    config = Config(database_url=postgres_url, release_storage_path=str(tmp_path), log_level="INFO")
    response = _client(config).get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "READY"


def test_readiness_endpoint_503_when_not_ready(tmp_path):
    config = Config(
        database_url="postgresql+psycopg://nobody:nothing@127.0.0.1:1/does_not_exist",
        release_storage_path=str(tmp_path),
        log_level="INFO",
    )
    response = _client(config).get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["data"]["status"] == "NOT_READY"
    # the API request itself still succeeded — it correctly determined NOT_READY
    assert body["success"] is True
