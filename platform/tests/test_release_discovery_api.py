import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from rah_platform.app import create_app
from rah_platform.config import Config

FIXTURES_ROOT = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "releases"


def _client(config: Config) -> TestClient:
    return TestClient(create_app(config))


def _config(migrated_db_url, storage_path) -> Config:
    return Config(database_url=migrated_db_url, release_storage_path=str(storage_path), log_level="INFO")


def test_scan_endpoint(db_engine, migrated_db_url, tmp_path):
    shutil.copytree(FIXTURES_ROOT / "valid-release-1.0.0", tmp_path / "valid-release-1.0.0")
    response = _client(_config(migrated_db_url, tmp_path)).post("/api/v1/release-candidates/scan")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["candidate_count"] == 1
    assert body["data"]["candidates"][0]["discovery_state"] == "READY_FOR_IMPORT"


def test_scan_endpoint_empty_body_also_accepted(db_engine, migrated_db_url, tmp_path):
    response = _client(_config(migrated_db_url, tmp_path)).post(
        "/api/v1/release-candidates/scan", json={"rescan_known_releases": True}
    )
    assert response.status_code == 200


def test_scan_endpoint_rejects_arbitrary_path_field(db_engine, migrated_db_url, tmp_path):
    response = _client(_config(migrated_db_url, tmp_path)).post(
        "/api/v1/release-candidates/scan", json={"path": "/etc"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "PLT-INPUT-003"


def test_list_and_get_candidate_endpoints(db_engine, migrated_db_url, tmp_path):
    shutil.copytree(FIXTURES_ROOT / "valid-release-1.0.0", tmp_path / "valid-release-1.0.0")
    client = _client(_config(migrated_db_url, tmp_path))
    client.post("/api/v1/release-candidates/scan")

    listed = client.get("/api/v1/release-candidates")
    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert len(items) == 1
    candidate_id = items[0]["candidate_id"]

    fetched = client.get(f"/api/v1/release-candidates/{candidate_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["candidate_id"] == candidate_id


def test_get_candidate_endpoint_not_found(db_engine, migrated_db_url, tmp_path):
    response = _client(_config(migrated_db_url, tmp_path)).get(
        "/api/v1/release-candidates/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLT-STORAGE-004"
