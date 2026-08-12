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
    )


def _client(migrated_db_url, tmp_path) -> TestClient:
    return TestClient(create_app(_config(migrated_db_url, tmp_path)))


@pytest.fixture()
def _teardown_compose_projects():
    projects: list[str] = []
    yield projects
    for project in projects:
        subprocess.run(["docker", "compose", "-p", project, "down"], capture_output=True, check=False)


def _install_valid_release(client: TestClient, port: int) -> dict:
    shutil.copytree(FIXTURES_ROOT / "valid-release-1.0.0", Path(client.app.state.config.release_storage_path) / "valid-release-1.0.0")
    client.post("/api/v1/release-candidates/scan")
    candidate_id = client.get("/api/v1/release-candidates").json()["data"]["items"][0]["candidate_id"]
    imported = client.post(f"/api/v1/release-candidates/{candidate_id}/import").json()["data"]
    response = client.post(
        f"/api/v1/releases/{imported['release_id']}/install",
        json={"configuration": {"APP_PORT": {"value": port}}, "requested_by": "operator:test"},
    )
    assert response.status_code == 202
    operation_id = response.json()["data"]["operation_id"]
    final = wait_for_terminal_operation(client.app.state.db_engine, operation_id)
    assert final["status"] == "SUCCEEDED"
    return imported


def test_verify_endpoint_returns_result(db_engine, migrated_db_url, tmp_path, _teardown_compose_projects):
    client = _client(migrated_db_url, tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported = _install_valid_release(client, 18920)

    response = client.post(f"/api/v1/applications/{imported['application']['id']}/verify")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "PASS"
    assert body["expected_release_id"] == imported["release_id"]


def test_get_verification_result_endpoint(db_engine, migrated_db_url, tmp_path, _teardown_compose_projects):
    client = _client(migrated_db_url, tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported = _install_valid_release(client, 18921)

    verify_response = client.post(f"/api/v1/applications/{imported['application']['id']}/verify")
    verification_run_id = verify_response.json()["data"]["verification_run_id"]

    response = client.get(f"/api/v1/verifications/{verification_run_id}")
    assert response.status_code == 200
    assert response.json()["data"]["verification_run_id"] == verification_run_id


def test_get_verification_result_endpoint_404_for_unknown_run(db_engine, migrated_db_url, tmp_path):
    client = _client(migrated_db_url, tmp_path)
    response = client.get("/api/v1/verifications/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLT-VERIFY-009"


def test_host_state_endpoint_is_read_only(db_engine, migrated_db_url, tmp_path, _teardown_compose_projects):
    client = _client(migrated_db_url, tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported = _install_valid_release(client, 18922)

    response = client.get(f"/api/v1/applications/{imported['application']['id']}/host-state")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["compose"]["matches"] is True
    assert any(c["state"] == "RUNNING" for c in body["containers"])


def test_reconcile_endpoint_returns_consistent(db_engine, migrated_db_url, tmp_path, _teardown_compose_projects):
    client = _client(migrated_db_url, tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported = _install_valid_release(client, 18923)

    response = client.post(f"/api/v1/applications/{imported['application']['id']}/reconcile")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "CONSISTENT"
