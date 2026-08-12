import shutil
import subprocess
from pathlib import Path

import docker
import pytest

from conftest import CONTRACTS_PATH, FIXTURES_ROOT, wait_for_terminal_operation
from rah_platform import application_query, backup, installation, operations, release_discovery, release_import, update, verification
from rah_platform.config import Config
from rah_platform.errors import UpdatePrerequisitesFailedError


def _config(tmp_path, **overrides) -> Config:
    defaults = dict(
        database_url="unused",
        release_storage_path=str(tmp_path / "releases"),
        log_level="INFO",
        contracts_path=str(CONTRACTS_PATH),
        deployments_path=str(tmp_path / "deployments"),
        install_script_timeout_seconds=30,
        backups_path=str(tmp_path / "backups"),
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
    projects: list[str] = []
    yield projects
    for project in projects:
        subprocess.run(["docker", "compose", "-p", project, "down"], capture_output=True, check=False)


def _install_1_0_0(db_engine, config, port):
    imported_1_0_0 = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    install_result = installation.install_application(
        db_engine, config, release_id=imported_1_0_0["release_id"], configuration={"APP_PORT": {"value": port}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, install_result["operation_id"])
    assert final["status"] == "SUCCEEDED"
    return imported_1_0_0


# --- Successful Update ---


def test_successful_update_activates_target_and_preserves_history(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported_1_0_0 = _install_1_0_0(db_engine, config, 19301)
    application_id = imported_1_0_0["application"]["id"]
    imported_1_1_0 = _import_golden_release(db_engine, config, "valid-release-1.1.0")

    result = update.update_application(
        db_engine, config, application_id=application_id, target_release_id=imported_1_1_0["release_id"], requested_by="operator:test"
    )
    assert result["status"] in ("PENDING", "RUNNING")
    final = wait_for_terminal_operation(db_engine, result["operation_id"], timeout=60)
    assert final["status"] == "SUCCEEDED"

    active = application_query.get_active_deployment(db_engine, application_id)
    assert active["release_id"] == imported_1_1_0["release_id"]

    releases = application_query.list_application_releases(db_engine, application_id)
    source_entry = next(r for r in releases["items"] if r["id"] == imported_1_0_0["release_id"])
    assert source_entry["deployment_state"] == "PREVIOUSLY_DEPLOYED"

    client = _docker_client()
    containers = client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    assert any(c.status == "running" and c.attrs["Config"]["Image"] == "golden-test-app-backend:1.1.0" for c in containers)

    backups_list = backup.list_backups(db_engine, application_id)
    assert len(backups_list["items"]) == 1
    assert backups_list["items"][0]["status"] == "VERIFIED"


# --- Backup Failure ---


def test_backup_failure_stops_update_before_execution(db_engine, tmp_path):
    config = _config(tmp_path)
    imported_1_0_0 = _install_1_0_0(db_engine, config, 19302)
    application_id = imported_1_0_0["application"]["id"]
    imported_target = _import_golden_release(db_engine, config, "update-backup-fails")

    result = update.update_application(
        db_engine, config, application_id=application_id, target_release_id=imported_target["release_id"], requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])

    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-UPDATE-002"

    active = application_query.get_active_deployment(db_engine, application_id)
    assert active["release_id"] == imported_1_0_0["release_id"]  # never touched

    assert backup.list_backups(db_engine, application_id)["items"] == []

    logs = operations.get_operation_logs(db_engine, result["operation_id"])
    assert not any("Update script exited" in entry["message"] for entry in logs["logs"])


# --- Configuration Preservation ---


def test_configuration_preservation_port_and_secret(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    _teardown_compose_projects.append("rah-secret-app")
    imported_source = _import_golden_release(db_engine, config, "install-with-secret")
    application_id = imported_source["application"]["id"]
    secret_value = "correct-horse-battery-staple-pl8a"

    install_result = installation.install_application(
        db_engine, config, release_id=imported_source["release_id"],
        configuration={"APP_PORT": {"value": 19303}, "ADMIN_PASSWORD": {"value": secret_value}},
        requested_by="operator:test",
    )
    final = wait_for_terminal_operation(db_engine, install_result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    imported_target = _import_golden_release(db_engine, config, "update-secret-app")
    result = update.update_application(
        db_engine, config, application_id=application_id, target_release_id=imported_target["release_id"], requested_by="operator:test"
    )
    update_final = wait_for_terminal_operation(db_engine, result["operation_id"], timeout=60)
    assert update_final["status"] == "SUCCEEDED"

    active = application_query.get_active_deployment(db_engine, application_id)
    assert active["release_id"] == imported_target["release_id"]

    env_path = Path(config.deployments_path) / "secret-app" / "compose" / ".env"
    rendered = env_path.read_text()
    assert "APP_PORT=19303" in rendered
    assert f"ADMIN_PASSWORD={secret_value}" in rendered

    logs = operations.get_operation_logs(db_engine, result["operation_id"])
    events = operations.get_operation_events(db_engine, result["operation_id"])
    import json
    assert secret_value not in json.dumps(logs)
    assert secret_value not in json.dumps(events)


# --- Update Script Failure ---


def test_update_script_failure_leaves_source_active(db_engine, tmp_path):
    config = _config(tmp_path)
    imported_1_0_0 = _install_1_0_0(db_engine, config, 19304)
    application_id = imported_1_0_0["application"]["id"]
    imported_target = _import_golden_release(db_engine, config, "update-script-fails")

    result = update.update_application(
        db_engine, config, application_id=application_id, target_release_id=imported_target["release_id"], requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])

    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-UPDATE-005"
    assert final["error"]["details"]["exit_code"] == 6

    active = application_query.get_active_deployment(db_engine, application_id)
    assert active["release_id"] == imported_1_0_0["release_id"]

    # the mandatory backup genuinely succeeded before the update script ran
    backups_list = backup.list_backups(db_engine, application_id)
    assert len(backups_list["items"]) == 1
    assert backups_list["items"][0]["status"] == "VERIFIED"


# --- Migration Failure ---


def test_migration_failure_leaves_source_active_but_host_genuinely_changed(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported_1_0_0 = _install_1_0_0(db_engine, config, 19305)
    application_id = imported_1_0_0["application"]["id"]
    imported_target = _import_golden_release(db_engine, config, "update-migration-fails")

    result = update.update_application(
        db_engine, config, application_id=application_id, target_release_id=imported_target["release_id"], requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])

    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-DATABASE-002"
    assert final["error"]["details"]["exit_code"] == 7

    active = application_query.get_active_deployment(db_engine, application_id)
    assert active["release_id"] == imported_1_0_0["release_id"]  # Registry never overwritten

    # the update script itself really did run and replace the container —
    # a genuine drift between "Registry still says 1.0.0" and "host is
    # actually running the target image" — exactly what PL7's
    # reconciliation exists to catch.
    reconciliation = verification.reconcile_application_state(db_engine, application_id)
    assert reconciliation["status"] == "DRIFT_DETECTED"


# --- Verification Failure After Update Script Success ---


def test_verification_failure_after_update_script_success_leaves_source_active(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported_1_0_0 = _install_1_0_0(db_engine, config, 19306)
    application_id = imported_1_0_0["application"]["id"]
    imported_target = _import_golden_release(db_engine, config, "update-verify-fails")

    result = update.update_application(
        db_engine, config, application_id=application_id, target_release_id=imported_target["release_id"], requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"], timeout=60)

    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-UPDATE-007"

    active = application_query.get_active_deployment(db_engine, application_id)
    assert active["release_id"] == imported_1_0_0["release_id"]  # target never becomes active

    client = _docker_client()
    containers = client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    assert any(c.status == "running" and c.attrs["Config"]["Image"] == "golden-test-app-backend:1.1.0" for c in containers)


# --- Update Prerequisites Failed ---


def test_update_prerequisites_failed_when_no_active_deployment(db_engine, tmp_path):
    config = _config(tmp_path)
    imported_target = _import_golden_release(db_engine, config, "valid-release-1.1.0")

    with pytest.raises(UpdatePrerequisitesFailedError) as exc_info:
        update.update_application(
            db_engine, config, application_id=imported_target["application"]["id"], target_release_id=imported_target["release_id"], requested_by="operator:test"
        )
    assert exc_info.value.code == "PLT-UPDATE-001"
    reasons = exc_info.value.details["blocking_reasons"]
    assert any(r["code"] == "PLT-TRANSITION-007" for r in reasons)


# --- Registry Commit Failure ---


def test_registry_commit_failure_reports_recovery_required(db_engine, tmp_path, monkeypatch, _teardown_compose_projects):
    config = _config(tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported_1_0_0 = _install_1_0_0(db_engine, config, 19307)
    application_id = imported_1_0_0["application"]["id"]
    imported_target = _import_golden_release(db_engine, config, "valid-release-1.1.0")

    monkeypatch.setattr(
        "rah_platform.installation.applications.update",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated registry failure")),
    )

    result = update.update_application(
        db_engine, config, application_id=application_id, target_release_id=imported_target["release_id"], requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"], timeout=60)

    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-UPDATE-008"
    assert final["error"]["details"]["recovery_required"] is True

    active = application_query.get_active_deployment(db_engine, application_id)
    assert active["release_id"] == imported_1_0_0["release_id"]  # not falsely marked active

    client = _docker_client()
    containers = client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    assert any(c.status == "running" and c.attrs["Config"]["Image"] == "golden-test-app-backend:1.1.0" for c in containers)
