import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import CONTRACTS_PATH, FIXTURES_ROOT, wait_for_terminal_operation
from rah_platform import backup, installation, release_discovery, release_import
from rah_platform.config import Config
from rah_platform.errors import ApplicationNotInstalledError, BackupNotFoundError


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


@pytest.fixture()
def _teardown_compose_projects():
    projects: list[str] = []
    yield projects
    for project in projects:
        subprocess.run(["docker", "compose", "-p", project, "down"], capture_output=True, check=False)


# --- Successful Backup ---


def test_successful_backup_creates_real_artifact_and_registry_row(db_engine, tmp_path, _teardown_compose_projects):
    """A standalone backup call, against an application whose *own*
    active release declares `database.backup_before_update` — real
    fresh-install of `valid-release-1.1.0` directly (it supports
    `fresh_install: true` too), since `valid-release-1.0.0` declares no
    backup entrypoint of its own.
    """
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.1.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    install_result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 19201}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, install_result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    result = backup.create_backup(
        db_engine, config, application_id=imported["application"]["id"], backup_type="DATABASE", verify_after_creation=True, requested_by="operator:test"
    )
    backup_final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert backup_final["status"] == "SUCCEEDED"

    backups_list = backup.list_backups(db_engine, imported["application"]["id"])
    assert len(backups_list["items"]) == 1
    created = backups_list["items"][0]
    assert created["status"] == "VERIFIED"
    assert created["verified"] is True
    assert created["backup_type"] == "DATABASE"
    assert Path(created["storage_path"]).is_file()
    assert len(created["checksum"]) == 64  # real sha256 hex digest

    fetched = backup.get_backup(db_engine, created["backup_id"])
    assert fetched == created


# --- Backup unsupported / not installed ---


def test_backup_unsupported_when_active_release_declares_no_backup_entrypoint(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    install_result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 19202}}, requested_by="operator:test"
    )
    wait_for_terminal_operation(db_engine, install_result["operation_id"])

    result = backup.create_backup(
        db_engine, config, application_id=imported["application"]["id"], backup_type="DATABASE", verify_after_creation=True, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "FAILED"
    assert final["error"]["code"] == "PLT-BACKUP-001"


def test_backup_requires_active_deployment(db_engine, tmp_path):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.1.0")

    with pytest.raises(ApplicationNotInstalledError) as exc_info:
        backup.create_backup(
            db_engine, config, application_id=imported["application"]["id"], backup_type="DATABASE", verify_after_creation=True, requested_by="operator:test"
        )
    assert exc_info.value.code == "PLT-APPLICATION-003"


def test_get_backup_not_found(db_engine):
    with pytest.raises(BackupNotFoundError) as exc_info:
        backup.get_backup(db_engine, "00000000-0000-0000-0000-000000000000")
    assert exc_info.value.code == "PLT-BACKUP-008"
