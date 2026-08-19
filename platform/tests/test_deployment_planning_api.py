import shutil

from fastapi.testclient import TestClient

from conftest import CONTRACTS_PATH, FIXTURES_ROOT, seed_active_deployment, seed_application, seed_release
from rah_platform import release_discovery, release_import
from rah_platform.app import create_app
from rah_platform.config import Config


def _config(migrated_db_url, storage_path) -> Config:
    return Config(
        database_url=migrated_db_url, release_storage_path=str(storage_path), log_level="INFO", contracts_path=str(CONTRACTS_PATH)
    )


def _client(migrated_db_url, storage_path) -> TestClient:
    return TestClient(create_app(_config(migrated_db_url, storage_path)))


def _import_via_api(client, tmp_path, directory_name="valid-release-1.0.0"):
    shutil.copytree(FIXTURES_ROOT / directory_name, tmp_path / directory_name)
    client.post("/api/v1/release-candidates/scan")
    candidate_id = next(
        c["candidate_id"]
        for c in client.get("/api/v1/release-candidates").json()["data"]["items"]
        if c["directory_name"] == directory_name
    )
    return client.post(f"/api/v1/release-candidates/{candidate_id}/import").json()["data"]


def test_installation_plan_endpoint(db_engine, migrated_db_url, tmp_path):
    client = _client(migrated_db_url, tmp_path)
    imported = _import_via_api(client, tmp_path)

    response = client.post(f"/api/v1/releases/{imported['release_id']}/installation-plan")
    assert response.status_code == 200
    assert response.json()["data"]["allowed"] is True


def test_validate_inputs_endpoint_unknown_key(db_engine, migrated_db_url, tmp_path):
    client = _client(migrated_db_url, tmp_path)
    imported = _import_via_api(client, tmp_path)

    response = client.post(
        f"/api/v1/releases/{imported['release_id']}/validate-inputs",
        json={"configuration": {"NOT_REAL": {"value": "x"}}},
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "PLT-INPUT-004"


def test_suggest_ports_endpoint(db_engine, migrated_db_url, tmp_path):
    client = _client(migrated_db_url, tmp_path)
    response = client.post("/api/v1/host/ports/suggestions", json={"count": 2})
    assert response.status_code == 200
    assert len(response.json()["data"]["suggestions"]) == 2


def test_update_plan_endpoint(db_engine, migrated_db_url, tmp_path):
    client = _client(migrated_db_url, tmp_path)
    app_id = seed_application(db_engine)
    v1 = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    v2 = seed_release(
        db_engine,
        application_id=app_id,
        version="1.1.0",
        supported_operations={"fresh_install": True, "update": True},
        accepted_installed_versions=["1.0.0"],
    )
    seed_active_deployment(db_engine, application_id=app_id, release_id=v1)

    response = client.post(f"/api/v1/applications/{app_id}/update-plan", json={"target_release_id": v2})
    assert response.status_code == 200
    assert response.json()["data"]["allowed"] is True
