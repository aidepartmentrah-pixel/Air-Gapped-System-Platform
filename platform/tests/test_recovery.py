import shutil
import subprocess
from pathlib import Path

import docker
import pytest

from conftest import CONTRACTS_PATH, FIXTURES_ROOT, wait_for_terminal_operation
from rah_platform import application_query, backup, installation, operations, recovery, release_discovery, release_import, update, verification
from rah_platform.config import Config
from rah_platform.errors import (
    BackupBelongsToAnotherApplicationError,
    RecoveryPrerequisitesFailedError,
    RecoveryUnsupportedError,
)


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


# --- Recovery after a real failed update ---


def test_recovery_after_failed_update_restores_host_state(db_engine, tmp_path, _teardown_compose_projects):
    """§9.22's "Verification Failure After Update Script Success" leaves
    real drift: the host is running the *target* image, but the Registry
    correctly still claims the *source* release is active. Recovery's
    job in Period A: repair the host to match the Registry — real
    `docker load` + `docker compose up` of the source's own real image,
    plus the backup's config restored — never changing which release is
    "active."
    """
    config = _config(tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")

    imported_source = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    application_id = imported_source["application"]["id"]
    install_result = installation.install_application(
        db_engine, config, release_id=imported_source["release_id"], configuration={"APP_PORT": {"value": 19500}}, requested_by="operator:test"
    )
    wait_for_terminal_operation(db_engine, install_result["operation_id"])

    imported_target = _import_golden_release(db_engine, config, "update-verify-fails")
    update_result = update.update_application(
        db_engine, config, application_id=application_id, target_release_id=imported_target["release_id"], requested_by="operator:test"
    )
    failed_operation = wait_for_terminal_operation(db_engine, update_result["operation_id"], timeout=60)
    assert failed_operation["status"] == "FAILED"
    assert failed_operation["error"]["code"] == "PLT-UPDATE-007"

    # real drift: source still active per the Registry, but the real
    # container is running the target's image.
    client = _docker_client()
    containers = client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    assert any(c.attrs["Config"]["Image"] == "golden-test-app-backend:1.1.0" for c in containers)
    reconciliation_before = verification.reconcile_application_state(db_engine, application_id)
    assert reconciliation_before["status"] == "DRIFT_DETECTED"

    # RECOVER only becomes available now, because of the real failure.
    actions = application_query.get_available_actions(db_engine, application_id)
    recover_action = next(a for a in actions["actions"] if a["action"] == "RECOVER")
    assert recover_action["allowed"] is True

    backups_list = backup.list_backups(db_engine, application_id)
    assert len(backups_list["items"]) == 1
    backup_id = backups_list["items"][0]["backup_id"]

    recovery_result = recovery.recover_application(
        db_engine, config, application_id=application_id, failed_operation_id=update_result["operation_id"],
        backup_id=backup_id, requested_by="operator:test",
    )
    recovery_final = wait_for_terminal_operation(db_engine, recovery_result["operation_id"], timeout=60)
    assert recovery_final["status"] == "SUCCEEDED"

    # §7.24: a separate operation record, distinct from the failed one.
    assert recovery_result["operation_id"] != update_result["operation_id"]

    # the active release never changed — recovery repairs the host, not the Registry.
    active = application_query.get_active_deployment(db_engine, application_id)
    assert active["release_id"] == imported_source["release_id"]

    # the real host now matches again.
    containers_after = client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    assert any(c.attrs["Config"]["Image"] == "golden-test-app-backend:1.0.0" and c.status == "running" for c in containers_after)

    reconciliation_after = verification.reconcile_application_state(db_engine, application_id)
    assert reconciliation_after["status"] == "CONSISTENT"

    backup_after = backup.get_backup(db_engine, backup_id)
    assert backup_after["status"] == "RESTORED"

    # both the failure and the recovery remain in history — nothing rewritten.
    failed_again = operations.get_operation(db_engine, update_result["operation_id"])
    assert failed_again["status"] == "FAILED"


# --- Standalone Backup Restore ---


def test_standalone_backup_restore(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported = _import_golden_release(db_engine, config, "valid-release-1.1.0")
    application_id = imported["application"]["id"]

    install_result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 19501}}, requested_by="operator:test"
    )
    wait_for_terminal_operation(db_engine, install_result["operation_id"])

    backup_result = backup.create_backup(
        db_engine, config, application_id=application_id, backup_type="DATABASE", verify_after_creation=True, requested_by="operator:test"
    )
    wait_for_terminal_operation(db_engine, backup_result["operation_id"])
    backup_id = backup.list_backups(db_engine, application_id)["items"][0]["backup_id"]

    restore_result = recovery.restore_backup(
        db_engine, config, application_id=application_id, backup_id=backup_id, requested_by="operator:test"
    )
    restore_final = wait_for_terminal_operation(db_engine, restore_result["operation_id"])
    assert restore_final["status"] == "SUCCEEDED"

    assert backup.get_backup(db_engine, backup_id)["status"] == "RESTORED"


# --- Wrong Application Backup ---


def test_wrong_application_backup_rejected(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    _teardown_compose_projects.append("rah-secret-app")

    imported_a = _import_golden_release(db_engine, config, "valid-release-1.1.0")
    install_a = installation.install_application(
        db_engine, config, release_id=imported_a["release_id"], configuration={"APP_PORT": {"value": 19502}}, requested_by="operator:test"
    )
    wait_for_terminal_operation(db_engine, install_a["operation_id"])
    backup_result = backup.create_backup(
        db_engine, config, application_id=imported_a["application"]["id"], backup_type="DATABASE", verify_after_creation=True, requested_by="operator:test"
    )
    wait_for_terminal_operation(db_engine, backup_result["operation_id"])
    backup_id = backup.list_backups(db_engine, imported_a["application"]["id"])["items"][0]["backup_id"]

    imported_b = _import_golden_release(db_engine, config, "install-with-secret")
    install_b = installation.install_application(
        db_engine, config, release_id=imported_b["release_id"],
        configuration={"APP_PORT": {"value": 19503}, "ADMIN_PASSWORD": {"value": "irrelevant"}}, requested_by="operator:test",
    )
    wait_for_terminal_operation(db_engine, install_b["operation_id"])

    with pytest.raises(BackupBelongsToAnotherApplicationError) as exc_info:
        recovery.restore_backup(
            db_engine, config, application_id=imported_b["application"]["id"], backup_id=backup_id, requested_by="operator:test"
        )
    assert exc_info.value.code == "PLT-BACKUP-007"


# --- Recover error paths ---


def test_recover_unsupported_recovery_mode(db_engine, tmp_path):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")

    with pytest.raises(RecoveryUnsupportedError) as exc_info:
        recovery.recover_application(
            db_engine, config, application_id=imported["application"]["id"], failed_operation_id="00000000-0000-0000-0000-000000000000",
            backup_id="00000000-0000-0000-0000-000000000000", recovery_mode="ROLLING_RESTART", requested_by="operator:test",
        )
    assert exc_info.value.code == "PLT-RECOVERY-001"


def test_recover_prerequisites_failed_when_operation_not_failed(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    _teardown_compose_projects.append("rah-golden-test-app")
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    application_id = imported["application"]["id"]

    install_result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 19504}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, install_result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    with pytest.raises(RecoveryPrerequisitesFailedError) as exc_info:
        recovery.recover_application(
            db_engine, config, application_id=application_id, failed_operation_id=install_result["operation_id"],
            backup_id="00000000-0000-0000-0000-000000000000", requested_by="operator:test",
        )
    assert exc_info.value.code == "PLT-RECOVERY-002"
