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


def test_install_endpoint_returns_202_then_reaches_succeeded(db_engine, migrated_db_url, tmp_path, _teardown_compose_projects):
    client = _client(migrated_db_url, tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")

    shutil.copytree(FIXTURES_ROOT / "valid-release-1.0.0", Path(client.app.state.config.release_storage_path) / "valid-release-1.0.0")
    client.post("/api/v1/release-candidates/scan")
    candidate_id = client.get("/api/v1/release-candidates").json()["data"]["items"][0]["candidate_id"]
    release_id = client.post(f"/api/v1/release-candidates/{candidate_id}/import").json()["data"]["release_id"]

    response = client.post(
        f"/api/v1/releases/{release_id}/install",
        json={"configuration": {"APP_PORT": {"value": 18810}}, "requested_by": "operator:test"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True
    operation_id = body["data"]["operation_id"]
    assert body["data"]["status"] in ("PENDING", "RUNNING")

    final = wait_for_terminal_operation(client.app.state.db_engine, operation_id)
    assert final["status"] == "SUCCEEDED"

    polled = client.get(f"/api/v1/operations/{operation_id}").json()["data"]
    assert polled["status"] == "SUCCEEDED"
