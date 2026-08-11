import uuid

from fastapi.testclient import TestClient

from rah_platform import operations
from rah_platform.app import create_app
from rah_platform.config import Config


def _client(config: Config) -> TestClient:
    return TestClient(create_app(config))


def _config(migrated_db_url) -> Config:
    return Config(database_url=migrated_db_url, release_storage_path="/tmp", log_level="INFO")


def test_get_operation_endpoint(db_engine, migrated_db_url):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=str(uuid.uuid4()), requested_by="operator:test"
    )
    response = _client(_config(migrated_db_url)).get(f"/api/v1/operations/{op['operation_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["operation_id"] == op["operation_id"]
    assert body["data"]["status"] == "PENDING"
    assert body["data"]["links"]["events"].endswith(f"/operations/{op['operation_id']}/events")


def test_get_operation_endpoint_not_found(db_engine, migrated_db_url):
    response = _client(_config(migrated_db_url)).get(f"/api/v1/operations/{uuid.uuid4()}")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "PLT-OPERATION-001"


def test_get_operation_events_endpoint(db_engine, migrated_db_url):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=str(uuid.uuid4()), requested_by="operator:test"
    )
    response = _client(_config(migrated_db_url)).get(f"/api/v1/operations/{op['operation_id']}/events")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["operation_id"] == op["operation_id"]
    assert body["data"]["events"][0]["event_type"] == "REQUEST_ACCEPTED"


def test_get_operation_logs_endpoint(db_engine, migrated_db_url):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=str(uuid.uuid4()), requested_by="operator:test"
    )
    response = _client(_config(migrated_db_url)).get(f"/api/v1/operations/{op['operation_id']}/logs")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["operation_id"] == op["operation_id"]
    assert len(body["data"]["logs"]) >= 1


def test_lock_conflict_returns_423_through_create_operation(db_engine, migrated_db_url):
    app_id = str(uuid.uuid4())
    operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    import pytest

    from rah_platform.errors import ApplicationLockedError

    with pytest.raises(ApplicationLockedError) as exc_info:
        operations.create_operation(
            db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:other"
        )
    assert exc_info.value.http_status == 423
