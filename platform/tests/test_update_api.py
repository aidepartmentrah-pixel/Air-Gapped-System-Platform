import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import CONTRACTS_PATH, FIXTURES_ROOT, wait_for_terminal_operation
from rah_platform.app import create_app
from rah_platform.config import Config


def _config(migrated_db_url, tmp_path) -> Config:
    return Config(
        database_url=migrated_db_url,
        release_storage_path=str(tmp_path / "releases"),
        log_level="INFO",
        contracts_path=str(CONTRACTS_PATH),
        deployments_path=str(tmp_path / "deployments"),
        install_script_timeout_seconds=30,
        backups_path=str(tmp_path / "backups"),
    )


def _client(migrated_db_url, tmp_path) -> TestClient:
    return TestClient(create_app(_config(migrated_db_url, tmp_path)))


@pytest.fixture()
def _teardown_compose_projects():
    projects: list[str] = []
    yield projects
    for project in projects:
        subprocess.run(["docker", "compose", "-p", project, "down"], capture_output=True, check=False)


def _import_via_api(client: TestClient, directory_name: str) -> dict:
    shutil.copytree(FIXTURES_ROOT / directory_name, Path(client.app.state.config.release_storage_path) / directory_name)
    client.post("/api/v1/release-candidates/scan")
    candidate_id = next(
        c["candidate_id"]
        for c in client.get("/api/v1/release-candidates").json()["data"]["items"]
        if c["directory_name"] == directory_name
    )
    return client.post(f"/api/v1/release-candidates/{candidate_id}/import").json()["data"]


def test_backup_endpoints_return_real_result(db_engine, migrated_db_url, tmp_path, _teardown_compose_projects):
    client = _client(migrated_db_url, tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported = _import_via_api(client, "valid-release-1.1.0")

    install_response = client.post(
        f"/api/v1/releases/{imported['release_id']}/install",
        json={"configuration": {"APP_PORT": {"value": 19320}}, "requested_by": "operator:test"},
    )
    assert install_response.status_code == 202
    wait_for_terminal_operation(db_engine, install_response.json()["data"]["operation_id"])

    application_id = imported["application"]["id"]
    backup_response = client.post(f"/api/v1/applications/{application_id}/backups")
    assert backup_response.status_code == 202
    backup_operation_id = backup_response.json()["data"]["operation_id"]
    final = wait_for_terminal_operation(db_engine, backup_operation_id)
    assert final["status"] == "SUCCEEDED"

    listed = client.get(f"/api/v1/applications/{application_id}/backups").json()["data"]
    assert len(listed["items"]) == 1
    backup_id = listed["items"][0]["backup_id"]

    fetched = client.get(f"/api/v1/backups/{backup_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["backup_id"] == backup_id


def test_update_endpoint_returns_202_then_succeeded(db_engine, migrated_db_url, tmp_path, _teardown_compose_projects):
    client = _client(migrated_db_url, tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")

    source = _import_via_api(client, "valid-release-1.0.0")
    install_response = client.post(
        f"/api/v1/releases/{source['release_id']}/install",
        json={"configuration": {"APP_PORT": {"value": 19321}}, "requested_by": "operator:test"},
    )
    wait_for_terminal_operation(db_engine, install_response.json()["data"]["operation_id"])

    target = _import_via_api(client, "valid-release-1.1.0")
    application_id = source["application"]["id"]

    update_response = client.post(
        f"/api/v1/applications/{application_id}/update",
        json={"target_release_id": target["release_id"], "requested_by": "operator:test"},
    )
    assert update_response.status_code == 202
    body = update_response.json()
    assert body["success"] is True
    operation_id = body["data"]["operation_id"]

    final = wait_for_terminal_operation(db_engine, operation_id, timeout=60)
    assert final["status"] == "SUCCEEDED"

    active = client.get(f"/api/v1/applications/{application_id}/active-deployment").json()["data"]
    assert active["release_id"] == target["release_id"]
