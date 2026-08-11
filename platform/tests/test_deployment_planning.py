import shutil
import socket

import pytest

from conftest import (
    CONTRACTS_PATH,
    FIXTURES_ROOT,
    seed_active_deployment,
    seed_application,
    seed_deployment_configuration,
    seed_release,
)
from rah_platform import deployment_planning, release_discovery, release_import
from rah_platform.config import Config


def _config(tmp_path) -> Config:
    return Config(database_url="unused", release_storage_path=str(tmp_path), log_level="INFO", contracts_path=str(CONTRACTS_PATH))


def _import_golden_release(db_engine, tmp_path, directory_name="valid-release-1.0.0"):
    shutil.copytree(FIXTURES_ROOT / directory_name, tmp_path / directory_name)
    scan = release_discovery.scan_releases(db_engine, str(tmp_path))
    candidate_id = next(c["candidate_id"] for c in scan["candidates"] if c["directory_name"] == directory_name)
    return release_import.import_release(db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test")


# --- Installation Plan ---


def test_installation_plan_for_known_golden_release(db_engine, tmp_path):
    imported = _import_golden_release(db_engine, tmp_path)
    plan = deployment_planning.prepare_installation(db_engine, imported["release_id"])

    assert plan["allowed"] is True
    assert plan["canonical_path"] == "/opt/rah/apps/golden-test-app"
    assert plan["compose_project_name"] == "rah-golden-test-app"
    assert plan["expected_services"] == ["backend"]
    assert "release_identity" in plan["verification_checks"]
    assert "docker_services" in plan["verification_checks"]
    inputs = {i["key"]: i for i in plan["configuration_inputs"]}
    assert inputs["APP_PORT"]["type"] == "port"
    assert inputs["APP_PORT"]["required"] is True


# --- Port Suggestion ---


def test_port_suggestion_skips_occupied_preferred_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupied.bind(("0.0.0.0", 18765))
        occupied.listen(1)

        result = deployment_planning.suggest_available_ports(count=1, preferred_ports=[18765])

    assert 18765 not in result["suggestions"]
    assert len(result["suggestions"]) == 1


# --- Port Race Revalidation ---


def test_port_suggestion_remains_provisional_not_a_reservation():
    result = deployment_planning.suggest_available_ports(count=1, preferred_ports=[18766])
    suggested_port = result["suggestions"][0]
    assert result["provisional"] is True

    # something else grabs the port after suggestion — the earlier
    # suggestion was never a reservation, so re-checking now must reflect
    # the real, current state
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupied.bind(("0.0.0.0", suggested_port))
        occupied.listen(1)

        assert deployment_planning._port_is_available(suggested_port) is False


# --- Missing Required Input ---


def test_missing_required_input_validation_fails(db_engine, tmp_path):
    imported = _import_golden_release(db_engine, tmp_path)
    result = deployment_planning.validate_deployment_inputs(db_engine, imported["release_id"], {})
    assert result["valid"] is False
    assert any(e["code"] == "PLT-INPUT-002" and e["key"] == "APP_PORT" for e in result["errors"])


# --- Invalid Datatype ---


def test_invalid_datatype_validation_fails(db_engine, tmp_path):
    imported = _import_golden_release(db_engine, tmp_path)
    result = deployment_planning.validate_deployment_inputs(
        db_engine, imported["release_id"], {"APP_PORT": {"value": "not-a-port"}}
    )
    assert result["valid"] is False
    assert any(e["code"] == "PLT-INPUT-003" and e["key"] == "APP_PORT" for e in result["errors"])


# --- Unknown Config Key ---


def test_unknown_config_key_rejected(db_engine, tmp_path):
    imported = _import_golden_release(db_engine, tmp_path)
    result = deployment_planning.validate_deployment_inputs(
        db_engine, imported["release_id"], {"NOT_A_REAL_KEY": {"value": "x"}}
    )
    assert result["valid"] is False
    assert any(e["code"] == "PLT-INPUT-004" and e["key"] == "NOT_A_REAL_KEY" for e in result["errors"])


# --- Secret Value ---


def test_secret_value_not_echoed_through_response(db_engine):
    app_id = seed_application(db_engine)
    release_id = seed_release(
        db_engine,
        application_id=app_id,
        version="1.0.0",
        supported_operations={"fresh_install": True},
        configuration_inputs=[
            {"key": "ADMIN_PASSWORD", "label": "Admin password", "type": "password", "required": True, "source": "operator", "secret": True}
        ],
    )
    plan = deployment_planning.prepare_installation(db_engine, release_id)
    admin_input = next(i for i in plan["configuration_inputs"] if i["key"] == "ADMIN_PASSWORD")
    assert admin_input["secret"] is True
    assert "current_value" not in admin_input
    assert "value" not in admin_input
    # the whole plan, serialized, must never contain a real secret value
    import json

    assert "ADMIN_PASSWORD_REAL_VALUE" not in json.dumps(plan)


# --- Update Plan ---


def test_update_plan_preserves_existing_configuration(db_engine):
    app_id = seed_application(db_engine)
    inputs = [
        {"key": "APP_PORT", "label": "Port", "type": "port", "required": True, "source": "operator", "secret": False},
        {"key": "ADMIN_PASSWORD", "label": "Admin password", "type": "password", "required": True, "source": "operator", "secret": True},
    ]
    v1 = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True}, configuration_inputs=inputs)
    v2 = seed_release(
        db_engine,
        application_id=app_id,
        version="1.1.0",
        supported_operations={"fresh_install": True, "update": True},
        accepted_installed_versions=["1.0.0"],
        configuration_inputs=inputs,
    )
    deployment_id = seed_active_deployment(db_engine, application_id=app_id, release_id=v1)
    seed_deployment_configuration(db_engine, deployment_id=deployment_id, key="APP_PORT", value="9001", source="operator")
    seed_deployment_configuration(db_engine, deployment_id=deployment_id, key="ADMIN_PASSWORD", secret=True, source="operator")

    plan = deployment_planning.prepare_update(db_engine, app_id, v2)

    port_input = next(i for i in plan["configuration_inputs"] if i["key"] == "APP_PORT")
    assert port_input["source"] == "preserved"
    assert port_input["current_value"] == "9001"

    secret_input = next(i for i in plan["configuration_inputs"] if i["key"] == "ADMIN_PASSWORD")
    assert secret_input["source"] == "preserved"
    assert secret_input["value_state"] == "PRESERVED"
    assert "current_value" not in secret_input


# --- Mandatory Backup ---


def test_mandatory_backup_appears_explicitly_in_update_plan(db_engine):
    app_id = seed_application(db_engine)
    v1 = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    v2 = seed_release(
        db_engine,
        application_id=app_id,
        version="1.1.0",
        supported_operations={"fresh_install": True, "update": True},
        accepted_installed_versions=["1.0.0"],
        database={"required": True, "backup_before_update": {"required": True, "entrypoint": "backup.sh"}},
    )
    seed_active_deployment(db_engine, application_id=app_id, release_id=v1)

    plan = deployment_planning.prepare_update(db_engine, app_id, v2)

    assert plan["backup"]["required"] is True
    assert plan["backup"]["supported"] is True


# --- Planning Safety ---


def test_planning_does_not_change_docker_or_registry_state(db_engine, tmp_path):
    import sqlalchemy as sa

    imported = _import_golden_release(db_engine, tmp_path)
    deployment_planning.prepare_installation(db_engine, imported["release_id"])
    deployment_planning.validate_deployment_inputs(db_engine, imported["release_id"], {"APP_PORT": {"value": 8501}})
    deployment_planning.suggest_available_ports(count=1)

    with db_engine.connect() as conn:
        deployments_count = conn.execute(sa.text("SELECT COUNT(*) FROM deployments")).scalar()
        operations_count = conn.execute(sa.text("SELECT COUNT(*) FROM operations WHERE operation_type != 'IMPORT'")).scalar()
    assert deployments_count == 0
    assert operations_count == 0


def test_update_planning_does_not_change_active_deployment(db_engine):
    app_id = seed_application(db_engine)
    v1 = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    v2 = seed_release(db_engine, application_id=app_id, version="1.1.0", supported_operations={"fresh_install": True, "update": True}, accepted_installed_versions=["1.0.0"])
    deployment_id = seed_active_deployment(db_engine, application_id=app_id, release_id=v1)

    deployment_planning.prepare_update(db_engine, app_id, v2)

    from rah_platform import application_query

    active = application_query.get_active_deployment(db_engine, app_id)
    assert active["deployment_id"] == deployment_id
    assert active["release_id"] == v1  # unchanged
