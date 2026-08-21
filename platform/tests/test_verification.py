import shutil
import subprocess
from pathlib import Path

import docker
import pytest
import sqlalchemy as sa

from conftest import CONTRACTS_PATH, FIXTURES_ROOT, seed_application, wait_for_terminal_operation
from rah_platform import application_query, installation, operations, release_discovery, release_import, verification
from rah_platform.config import Config
from rah_platform.errors import NoActiveDeploymentError, VerificationRunNotFoundError


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


def _new_verify_operation(db_engine, application_id: str) -> str:
    operation = operations.create_operation(
        db_engine, operation_type="VERIFY", application_id=application_id, requested_by="operator:test"
    )
    operations.start_operation(db_engine, operation["operation_id"])
    return operation["operation_id"]


def _run_manual_verification(db_engine, *, application_id: str, expected_release_id: str, configuration_values: dict | None = None) -> dict:
    """Mirrors `verification.verify_deployment`'s own contract for a
    directly-created `VERIFY` operation: `run_verification` only writes
    the verification record, it never transitions the operation to a
    terminal state — that is the caller's responsibility (real callers
    always go through `verify_deployment`, which does exactly this).
    Skipping this step would leave the operation `RUNNING` forever and
    permanently hold the application's operation lock.
    """
    operation_id = _new_verify_operation(db_engine, application_id)
    result = verification.run_verification(
        db_engine,
        application_id=application_id,
        expected_release_id=expected_release_id,
        verification_type="MANUAL",
        operation_id=operation_id,
        configuration_values=configuration_values,
    )
    if result["status"] == "PASS":
        operations.succeed_operation(db_engine, operation_id)
    else:
        from rah_platform.errors import MandatoryVerificationFailedError

        operations.fail_operation(
            db_engine,
            operation_id,
            MandatoryVerificationFailedError(
                "One or more mandatory verification checks failed.",
                stage="VERIFYING",
                details={"verification_run_id": result["verification_run_id"], "summary": result["summary"]},
            ),
        )
    return result


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


@pytest.fixture()
def _teardown_manual_containers():
    """Containers started directly via docker-py (not `docker compose`) to
    simulate host drift that a compose project alone can't produce —
    removed after the test regardless of outcome.
    """
    containers = []
    yield containers
    for container in containers:
        try:
            container.remove(force=True)
        except docker.errors.NotFound:
            pass


# --- Healthy Installation ---


def test_healthy_installation_produces_passing_verification(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18901}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    events = operations.get_operation_events(db_engine, result["operation_id"])
    verification_event = next(e for e in events["events"] if e["event_type"] == "VERIFICATION_COMPLETED")
    assert verification_event["status"] == "PASS"
    verification_run_id = verification_event["details"]["verification_run_id"]

    stored = verification.get_verification_result(db_engine, verification_run_id)
    assert stored["status"] == "PASS"
    for key in verification.MANDATORY_CHECK_KEYS:
        check = next(c for c in stored["checks"] if c["check_key"] == key)
        # `persistent_configuration` is honestly NOT_APPLICABLE on a fresh
        # install — there is no prior deployment yet to compare against
        # (Registry commit happens *after* this verification run).
        expected = {"PASS", "NOT_APPLICABLE"} if key == "persistent_configuration" else {"PASS"}
        assert check["status"] in expected, check


# --- Failed Backend Health ---


def test_failed_backend_health_check(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "backend-health-fails")
    _teardown_compose_projects.append("rah-health-fail-app")

    # Uses the real install path (not a raw subprocess call) so the
    # container is started exactly as Platform starts it in production —
    # configuration rendered to canonical_path, RAH_ACTIVE_DEPLOYMENT_PATH
    # passed to the script. The operation is expected to end FAILED (the
    # backend never becomes healthy), but the container itself stays up
    # for this test's own manual verification below.
    install_result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 8501}}, requested_by="operator:test"
    )
    wait_for_terminal_operation(db_engine, install_result["operation_id"])

    application_id = imported["application"]["id"]
    result = _run_manual_verification(
        db_engine,
        application_id=application_id,
        expected_release_id=imported["release_id"],
        configuration_values={"APP_PORT": "8501"},
    )

    assert result["status"] == "FAIL"
    backend_health = next(c for c in result["checks"] if c["check_key"] == "backend_health")
    assert backend_health["status"] == "FAIL"


# --- Missing Container ---


def test_missing_container_detected(db_engine, tmp_path):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    # deliberately never installed — no real containers exist for this
    # Release's compose project.

    application_id = imported["application"]["id"]
    result = _run_manual_verification(
        db_engine,
        application_id=application_id,
        expected_release_id=imported["release_id"],
        configuration_values={"APP_PORT": "18902"},
    )

    assert result["status"] == "FAIL"
    existence = next(c for c in result["checks"] if c["check_key"] == "container_existence")
    assert existence["status"] == "FAIL"
    assert "backend" in existence["evidence"]["missing_services"]


# --- Wrong Image Tag ---


def test_wrong_image_tag_detected(db_engine, tmp_path, _teardown_manual_containers):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _import_golden_release(db_engine, config, "valid-release-1.1.0")

    client = _docker_client()
    for directory_name in ("valid-release-1.0.0", "valid-release-1.1.0"):
        archive = Path(config.release_storage_path) / directory_name / "docker-images" / "backend.tar"
        with open(archive, "rb") as f:
            client.images.load(f.read())

    container = client.containers.run(
        "golden-test-app-backend:1.1.0",
        detach=True,
        ports={"8080/tcp": 18903},
        labels={"com.docker.compose.project": "rah-golden-test-app", "com.docker.compose.service": "backend"},
    )
    _teardown_manual_containers.append(container)

    application_id = imported["application"]["id"]
    result = _run_manual_verification(
        db_engine,
        application_id=application_id,
        expected_release_id=imported["release_id"],
        configuration_values={"APP_PORT": "18903"},
    )

    assert result["status"] == "FAIL"
    tag_check = next(c for c in result["checks"] if c["check_key"] == "image_tags")
    assert tag_check["status"] == "FAIL"
    assert tag_check["evidence"]["mismatches"][0]["observed"] == "golden-test-app-backend:1.1.0"


# --- Changed Port ---


def test_changed_port_detected(db_engine, tmp_path, _teardown_compose_projects, _teardown_manual_containers):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18904}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    client = _docker_client()
    for c in client.containers.list(all=True, filters={"label": "com.docker.compose.project=rah-golden-test-app"}):
        c.remove(force=True)
    replacement = client.containers.run(
        "golden-test-app-backend:1.0.0",
        detach=True,
        ports={"8080/tcp": 18906},
        labels={"com.docker.compose.project": "rah-golden-test-app", "com.docker.compose.service": "backend"},
    )
    _teardown_manual_containers.append(replacement)

    application_id = imported["application"]["id"]
    verify_result = _run_manual_verification(
        db_engine, application_id=application_id, expected_release_id=imported["release_id"]
    )

    assert verify_result["status"] == "FAIL"
    port_check = next(c for c in verify_result["checks"] if c["check_key"] == "selected_port")
    assert port_check["status"] == "FAIL"
    assert port_check["evidence"]["expected"] == 18904
    assert port_check["evidence"]["observed"] == 18906


# --- Manual Container Stop ---


def test_manual_container_stop_detected(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18907}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    client = _docker_client()
    containers = client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    for c in containers:
        c.stop()

    application_id = imported["application"]["id"]
    verify_result = _run_manual_verification(
        db_engine, application_id=application_id, expected_release_id=imported["release_id"]
    )

    assert verify_result["status"] == "FAIL"
    health_check = next(c for c in verify_result["checks"] if c["check_key"] == "container_health")
    assert health_check["status"] == "FAIL"
    assert "backend" in health_check["evidence"]["not_running"]


# --- Verification History ---


def test_verification_history_preserves_earlier_failure(db_engine, tmp_path, _teardown_compose_projects):
    """§7.25: "A later passing verification shall not erase an earlier
    failure." Stop the container (a real FAIL), then start it again (a
    real PASS), and confirm both runs are independently retrievable.
    """
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18908}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    application_id = imported["application"]["id"]
    client = _docker_client()
    containers = client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    for c in containers:
        c.stop()

    failing_result = _run_manual_verification(
        db_engine, application_id=application_id, expected_release_id=imported["release_id"]
    )
    assert failing_result["status"] == "FAIL"

    for c in containers:
        c.start()

    passing_result = _run_manual_verification(
        db_engine, application_id=application_id, expected_release_id=imported["release_id"]
    )
    assert passing_result["status"] == "PASS"

    assert failing_result["verification_run_id"] != passing_result["verification_run_id"]
    still_failed = verification.get_verification_result(db_engine, failing_result["verification_run_id"])
    assert still_failed["status"] == "FAIL"


# --- Reconciliation: five states ---


def test_reconcile_unknown_when_no_active_deployment(db_engine):
    application_id = seed_application(db_engine)
    result = verification.reconcile_application_state(db_engine, application_id)
    assert result["status"] == "UNKNOWN"


def test_reconcile_consistent_after_healthy_install(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18909}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    reconciliation = verification.reconcile_application_state(db_engine, imported["application"]["id"])
    assert reconciliation["status"] == "CONSISTENT"
    assert reconciliation["drift_items"] == []


def test_reconcile_partially_running_multi_service(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "multi-service-app")
    _teardown_compose_projects.append("rah-multi-service-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18910}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    client = _docker_client()
    containers = client.containers.list(
        filters={"label": ["com.docker.compose.project=rah-multi-service-app", "com.docker.compose.service=worker"]}
    )
    for c in containers:
        c.stop()

    reconciliation = verification.reconcile_application_state(db_engine, imported["application"]["id"])
    assert reconciliation["status"] == "PARTIALLY_RUNNING"


def test_reconcile_drift_detected_when_container_stopped(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18911}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    client = _docker_client()
    for c in client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"}):
        c.stop()

    reconciliation = verification.reconcile_application_state(db_engine, imported["application"]["id"])
    assert reconciliation["status"] == "DRIFT_DETECTED"
    assert any(item["type"] == "CONTAINER_NOT_RUNNING" for item in reconciliation["drift_items"])


def test_reconcile_unreachable_when_docker_inspection_fails(db_engine, tmp_path, _teardown_compose_projects, monkeypatch):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18912}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    def _raise(*_args, **_kwargs):
        raise RuntimeError("simulated Docker Engine unreachable")

    monkeypatch.setattr("rah_platform.verification._containers_by_service", _raise)

    reconciliation = verification.reconcile_application_state(db_engine, imported["application"]["id"])
    assert reconciliation["status"] == "UNREACHABLE"
    assert any(item["type"] == "DOCKER_UNREACHABLE" for item in reconciliation["drift_items"])


# --- Read-Only Host Inspection ---


def test_inspect_host_state_is_read_only(db_engine, tmp_path, _teardown_compose_projects):
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18913}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    application_id = imported["application"]["id"]
    with db_engine.connect() as conn:
        operation_count_before = conn.execute(
            sa.select(sa.func.count()).select_from(operations.operations)
        ).scalar()

    host_state = verification.inspect_host_state(db_engine, application_id)
    assert host_state["compose"]["matches"] is True
    assert any(c["state"] == "RUNNING" for c in host_state["containers"])

    client = _docker_client()
    running_before = {
        c.id for c in client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    }

    # calling it again must not change anything: no new operation, no new
    # container, no restart.
    verification.inspect_host_state(db_engine, application_id)
    running_after = {
        c.id for c in client.containers.list(filters={"label": "com.docker.compose.project=rah-golden-test-app"})
    }
    assert running_before == running_after

    with db_engine.connect() as conn:
        operation_count_after = conn.execute(
            sa.select(sa.func.count()).select_from(operations.operations)
        ).scalar()
    assert operation_count_after == operation_count_before


# --- expected_release_id inference / error paths ---


def test_resolve_expected_release_infers_release_id_not_deployment_id(db_engine, tmp_path, _teardown_compose_projects):
    """Regression test for the bug where `_resolve_expected_release`
    returned `active_deployment_id` instead of the deployment's
    `release_id` — `verify_deployment` with no `expected_release_id`
    must resolve to a real Release, not a deployment identifier.
    """
    config = _config(tmp_path)
    imported = _import_golden_release(db_engine, config, "valid-release-1.0.0")
    _teardown_compose_projects.append("rah-golden-test-app")

    result = installation.install_application(
        db_engine, config, release_id=imported["release_id"], configuration={"APP_PORT": {"value": 18914}}, requested_by="operator:test"
    )
    final = wait_for_terminal_operation(db_engine, result["operation_id"])
    assert final["status"] == "SUCCEEDED"

    active = application_query.get_active_deployment(db_engine, imported["application"]["id"])
    assert active["release_id"] != active["deployment_id"]

    verify_result = verification.verify_deployment(
        db_engine, config, application_id=imported["application"]["id"], requested_by="operator:test"
    )
    assert verify_result["expected_release_id"] == imported["release_id"]
    assert verify_result["expected_release_id"] != active["deployment_id"]


def test_no_active_deployment_error_when_expected_release_omitted(db_engine, tmp_path):
    config = _config(tmp_path)
    application_id = seed_application(db_engine)

    with pytest.raises(NoActiveDeploymentError) as exc_info:
        verification.verify_deployment(db_engine, config, application_id=application_id, requested_by="operator:test")
    assert exc_info.value.code == "PLT-VERIFY-010"


def test_get_verification_result_not_found(db_engine):
    with pytest.raises(VerificationRunNotFoundError) as exc_info:
        verification.get_verification_result(db_engine, "00000000-0000-0000-0000-000000000000")
    assert exc_info.value.code == "PLT-VERIFY-009"
