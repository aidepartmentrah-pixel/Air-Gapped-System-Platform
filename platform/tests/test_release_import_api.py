import shutil

from fastapi.testclient import TestClient

from conftest import CONTRACTS_PATH, FIXTURES_ROOT
from rah_platform.app import create_app
from rah_platform.config import Config


def _config(migrated_db_url, storage_path) -> Config:
    return Config(
        database_url=migrated_db_url,
        release_storage_path=str(storage_path),
        log_level="INFO",
        contracts_path=str(CONTRACTS_PATH),
    )


def _client(config: Config) -> TestClient:
    return TestClient(create_app(config))


def test_import_endpoint_success(db_engine, migrated_db_url, tmp_path):
    shutil.copytree(FIXTURES_ROOT / "valid-release-1.0.0", tmp_path / "valid-release-1.0.0")
    client = _client(_config(migrated_db_url, tmp_path))
    client.post("/api/v1/release-candidates/scan")
    candidate_id = client.get("/api/v1/release-candidates").json()["data"]["items"][0]["candidate_id"]

    response = client.post(
        f"/api/v1/release-candidates/{candidate_id}/import", json={"requested_by": "operator:test"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["application"]["slug"] == "golden-test-app"


def test_import_endpoint_failed_compliance_returns_structured_error(db_engine, migrated_db_url, tmp_path):
    shutil.copytree(FIXTURES_ROOT / "failed-compliance", tmp_path / "failed-compliance")
    client = _client(_config(migrated_db_url, tmp_path))
    client.post("/api/v1/release-candidates/scan")
    candidate_id = client.get("/api/v1/release-candidates").json()["data"]["items"][0]["candidate_id"]

    response = client.post(f"/api/v1/release-candidates/{candidate_id}/import")
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "PLT-IMPORT-004"


def test_import_endpoint_unknown_candidate_404(db_engine, migrated_db_url, tmp_path):
    client = _client(_config(migrated_db_url, tmp_path))
    response = client.post("/api/v1/release-candidates/00000000-0000-0000-0000-000000000000/import")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLT-STORAGE-004"


# --- Scan reflects Registry state after import (closes the PL2 "ALREADY_IMPORTED not reachable" gap) ---


def test_rescan_after_import_reports_already_imported(db_engine, migrated_db_url, tmp_path):
    shutil.copytree(FIXTURES_ROOT / "valid-release-1.0.0", tmp_path / "valid-release-1.0.0")
    client = _client(_config(migrated_db_url, tmp_path))
    client.post("/api/v1/release-candidates/scan")
    candidate_id = client.get("/api/v1/release-candidates").json()["data"]["items"][0]["candidate_id"]
    client.post(f"/api/v1/release-candidates/{candidate_id}/import")

    rescanned = client.post("/api/v1/release-candidates/scan").json()["data"]["candidates"][0]
    assert rescanned["discovery_state"] == "ALREADY_IMPORTED"
    assert rescanned["already_imported"] is True
