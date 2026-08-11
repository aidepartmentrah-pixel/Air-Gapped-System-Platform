from fastapi.testclient import TestClient

from conftest import seed_active_deployment, seed_application, seed_release
from rah_platform.app import create_app
from rah_platform.config import Config


def _client(migrated_db_url) -> TestClient:
    config = Config(database_url=migrated_db_url, release_storage_path="/tmp", log_level="INFO")
    return TestClient(create_app(config))


def test_list_applications_endpoint(db_engine, migrated_db_url):
    seed_application(db_engine, slug="my-app")
    response = _client(migrated_db_url).get("/api/v1/applications")
    assert response.status_code == 200
    assert any(a["slug"] == "my-app" for a in response.json()["data"]["items"])


def test_get_application_endpoint_not_found(db_engine, migrated_db_url):
    response = _client(migrated_db_url).get("/api/v1/applications/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLT-APPLICATION-001"


def test_actions_endpoint_with_target_release_id(db_engine, migrated_db_url):
    app_id = seed_application(db_engine)
    release_id = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})

    response = _client(migrated_db_url).get(f"/api/v1/applications/{app_id}/actions?target_release_id={release_id}")
    assert response.status_code == 200
    actions = {a["action"]: a for a in response.json()["data"]["actions"]}
    assert actions["INSTALL"]["allowed"] is True


def test_active_deployment_endpoint(db_engine, migrated_db_url):
    app_id = seed_application(db_engine)
    release_id = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    seed_active_deployment(db_engine, application_id=app_id, release_id=release_id)

    response = _client(migrated_db_url).get(f"/api/v1/applications/{app_id}/active-deployment")
    assert response.status_code == 200
    assert response.json()["data"]["release_id"] == release_id


def test_release_endpoint(db_engine, migrated_db_url):
    app_id = seed_application(db_engine)
    release_id = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})

    response = _client(migrated_db_url).get(f"/api/v1/releases/{release_id}")
    assert response.status_code == 200
    assert response.json()["data"]["version"] == "1.0.0"
