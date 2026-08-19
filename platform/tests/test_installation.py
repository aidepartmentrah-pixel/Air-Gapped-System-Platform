import json
import shutil
import socket
import subprocess
from pathlib import Path

import docker
import pytest
import sqlalchemy as sa

from conftest import CONTRACTS_PATH, FIXTURES_ROOT, wait_for_terminal_operation
from rah_platform import application_query, installation, operations, release_discovery, release_import
from rah_platform.config import Config
from rah_platform.errors import ApplicationLockedError, PortUnavailableError


def _config(tmp_path, **overrides) -> Config:
    defaults = dict(
        database_url="unused",
        release_storage_path=str(tmp_path / "releases"),
        log_level="INFO",
        contracts_path=str(CONTRACTS_PATH),
        deployments_path=str(tmp_path / "deployments"),
        install_script_timeout_seconds=30,
    )
    defaults.update(overrides)
    return Config(**defaults)


def _import_golden_release(db_engine, config, directory_name):
    shutil.copytree(FIXTURES_ROOT / directory_name, Path(config.release_storage_path) / directory_name)
    scan = release_discovery.scan_releases(db_engine, config.release_storage_path)
    candidate_id = next(c["candidate_id"] for c in scan["candidates"] if c["directory_name"] == directory_name)
    return release_import.import_release(db_engine, config, candidate_id=candidate_id, requested_by="operator:test")


def _docker_client():
    return docker.from_env()


@pytest.fixture()
def _teardown_compose_projects():
    """Real containers/networks started by a real install script — torn
    down after the test so port numbers and compose project names are
    safe to reuse across the suite.
    """
    projects: list[str] = []
    yield projects
    for project in projects:
        subprocess.run(["docker", "compose", "-p", project, "down"], capture_output=True, check=False)


# --- Successful Install ---


def test_successful_install(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18801}}, requested_by="operator:test"
    )
    assert result["status"] in ("PENDING", "RUNNING")

    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    client = _docker_client()
    containers = client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    assert any(c.status == "running" for c in containers)

    active = application_query.get_active_deployment(db_engine, imported["application"]["id"])
    assert active is not None
    assert active["release_id"] == imported["release_id"]


# --- Installation Script Failure ---


def test_installation_script_failure(db_engine, tmp_path):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "install-script-fails")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18802}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])

    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-INSTALL-005"
    assert final["error"]["details"]["exit_code"] == 7

    application = application_query.get_application(db_engine, imported["application"]["id"])
    assert application["active_deployment"] is None

    logs = operations.get_operation_logs(db_engine, result["operation_id"])
    assert len(logs["logs"]) > 0


# --- Port Conflict Immediately Before Execution ---


def test_port_conflict_immediately_before_execution_stops_before_script(db_engine, tmp_path):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupied.bind(("0.0.0.0", 18803))
        occupied.listen(1)

        with pytest.raises(PortUnavailableError) as exc_info:
            installation.install_application(
                db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18803}}, requested_by="operator:test"
            )
    assert exc_info.value.code == "PLT-CONFIG-004"

    # no operation was ever created — execution stopped before the lock
    with db_engine.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM operations WHERE operation_type = 'INSTALL'")).scalar()
    assert count == 0


# --- Missing Script ---


def test_missing_script_fails_safely(db_engine, tmp_path):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "missing-install-script")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18804}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])

    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-INSTALL-004"


# --- Script Timeout ---


def test_script_timeout_fails_predictably(db_engine, tmp_path):
    config = _config(tmp_path, install_script_timeout_seconds=2)
    imported = _import_golden_release(db_engine, config, "install-script-timeout")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18805}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"], timeout=15)

    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-SCRIPT-003"


# --- Operation Lock ---


def test_operation_lock_rejects_second_install(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    first = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18806}}, requested_by="operator:test"
    )
    assert first["status"] in ("PENDING", "RUNNING")

    with pytest.raises(ApplicationLockedError):
        installation.install_application(
            db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18807}}, requested_by="operator:other"
        )

    wait_for_terminal_operation(db_engine, first["operation_id"])


# --- Secret Handling ---


def test_secret_does_not_leak_into_events_or_logs(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "install-with-secret")
    _teardown_compose_projects.append("rah-secret-app")

    secret_value = "correct-horse-battery-staple-42"
    result = installation.install_application(
        db_engine,
        config,
        release_id=imported["release_id"],
        configuration={"APP_PORT": {"value": 18808}, "ADMIN_PASSWORD": {"value": secret_value}},
        requested_by="operator:test",
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    logs = operations.get_operation_logs(db_engine, result["operation_id"])
    events = operations.get_operation_events(db_engine, result["operation_id"])

    assert secret_value not in json.dumps(logs)
    assert secret_value not in json.dumps(events)

    # the secret was still real inside the deployment's rendered .env —
    # the running container legitimately needs it, only *history* must
    # never contain it
    env_path = f"{config.deployments_path}/secret-app/compose/.env"
    assert secret_value in open(env_path).read()


# --- Registry Commit Failure ---


def test_registry_commit_failure_reports_reconciliation_required(db_engine, tmp_path, monkeypatch, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    monkeypatch.setattr(
        "rah_platform.installation.applications.update",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated registry failure")),
    )

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18809}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])

    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-INSTALL-007"
    assert final["error"]["details"]["reconciliation_required"] is True

    application = application_query.get_application(db_engine, imported["application"]["id"])
    assert application["active_deployment"] is None  # not falsely marked active

    # the host really did change (script + verification succeeded) —
    # confirm the container is genuinely running despite the Platform
    # not being able to claim it
    client = _docker_client()
    containers = client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    assert any(c.status == "running" for c in containers)
