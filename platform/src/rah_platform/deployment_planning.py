"""Deployment Planning and Configuration — PL5.

Describes exactly what an installation or update *would* do, without
doing any of it — §3.6/§3.8's own words: "Preparation shall not execute
installation scripts" / "shall not modify the active deployment." Nothing
here touches Docker, `operations`, or `deployments`; the only writes any
function in this module performs are none.

Port checks are real, live checks against this host (`socket.bind`), not
approximated — §7.17's Port-State Rule is explicit that "a port
suggestion is not a reservation," so every suggestion here is
provisional by construction: the same check re-run later (at real
install time, in `PL6`) is what actually matters.
"""

from __future__ import annotations

import ipaddress
import socket
import uuid
from urllib.parse import urlparse

from rah_platform.application_query import (
    get_application_row,
    get_available_actions,
    get_release_row,
    get_storage_state,
)
from rah_platform.models import deployment_configuration, deployments, releases

# --- Port availability ---


def _port_is_available(port: int, host: str = "0.0.0.0") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def suggest_available_ports(
    *, count: int = 1, minimum: int = 1024, maximum: int = 65535, preferred_ports: list[int] | None = None
) -> dict:
    suggestions = []
    candidates = list(preferred_ports or []) + [p for p in range(minimum, maximum + 1) if p not in (preferred_ports or [])]
    for port in candidates:
        if len(suggestions) >= count:
            break
        if minimum <= port <= maximum and _port_is_available(port):
            suggestions.append(port)
    return {"suggestions": suggestions, "provisional": True}


# --- Configuration input classification and validation ---


def _classify_input(input_decl: dict, preserved: dict | None) -> dict:
    key = input_decl["key"]
    source = input_decl["source"]
    secret = bool(input_decl.get("secret", False))

    entry = {
        "key": key,
        "label": input_decl["label"],
        "type": input_decl["type"],
        "required": input_decl["required"],
        "secret": secret,
        "source": source,
    }

    if preserved and key in preserved:
        entry["source"] = "preserved"
        if secret:
            entry["value_state"] = "PRESERVED"
        else:
            entry["current_value"] = preserved[key]
        return entry

    if secret:
        entry["value_state"] = "REQUIRED" if source == "operator" else "WILL_GENERATE"
        return entry

    if source == "fixed":
        entry["current_value"] = input_decl.get("default")
    else:
        entry["current_value"] = None

    return entry


def _preserved_configuration(engine, deployment_id: str | None) -> dict:
    """Non-secret preserved values, keyed by config key. Secret keys are
    tracked separately (`_preserved_secrets`) so they never pass through
    a plain dict that might get logged or echoed.
    """
    if not deployment_id:
        return {}
    with engine.connect() as conn:
        rows = conn.execute(
            deployment_configuration.select().where(
                deployment_configuration.c.deployment_id == deployment_id,
                deployment_configuration.c.secret.is_(False),
            )
        ).mappings().all()
    return {r["key"]: r["value"] for r in rows}


def _preserved_secret_keys(engine, deployment_id: str | None) -> set[str]:
    if not deployment_id:
        return set()
    with engine.connect() as conn:
        rows = conn.execute(
            deployment_configuration.select().where(
                deployment_configuration.c.deployment_id == deployment_id,
                deployment_configuration.c.secret.is_(True),
            )
        ).mappings().all()
    return {r["key"] for r in rows}


def _configuration_inputs(manifest: dict, preserved_values: dict, preserved_secret_keys: set[str]) -> list[dict]:
    merged_preserved = {**preserved_values, **{k: None for k in preserved_secret_keys}}
    return [_classify_input(decl, merged_preserved) for decl in manifest["configuration"]["inputs"]]


def _verification_checks(manifest: dict) -> list[str]:
    baseline = ["release_identity", "docker_services"]
    declared = manifest.get("verification", {}).get("required_checks", [])
    return baseline + [c for c in declared if c not in baseline]


def _expected_services(manifest: dict) -> list[str]:
    return [image["service"] for image in manifest["docker"]["images"]]


# --- Installation planning ---


def prepare_installation(engine, release_id: str) -> dict:
    with engine.connect() as conn:
        release_row = get_release_row(conn, release_id)
        application_row = get_application_row(conn, release_row["application_id"])

    manifest = release_row["manifest"]
    blocking_issues = []

    with engine.connect() as conn:
        release_storage_state = get_storage_state(conn, release_row)
    if release_storage_state != "AVAILABLE":
        blocking_issues.append({"code": "PLT-RELEASE-002", "message": "The selected Release Package is not available."})

    if application_row["active_deployment_id"]:
        blocking_issues.append({"code": "PLT-APPLICATION-002", "message": "The application is already installed."})

    if not manifest["deployment"]["supported_operations"].get("fresh_install", False):
        blocking_issues.append({"code": "PLT-TRANSITION-001", "message": "Fresh installation is not supported by this Release."})

    configuration_inputs = _configuration_inputs(manifest, {}, set())

    return {
        "plan_id": str(uuid.uuid4()),
        "operation_type": "INSTALL",
        "application": {"id": application_row["application_id"], "slug": application_row["slug"]},
        "source_release": None,
        "target_release": {"id": release_row["release_id"], "version": release_row["version"]},
        "allowed": not blocking_issues,
        "blocking_issues": blocking_issues,
        "canonical_path": manifest["deployment"]["canonical_path"],
        "compose_project_name": manifest["deployment"]["compose_project_name"],
        "configuration_inputs": configuration_inputs,
        "expected_services": _expected_services(manifest),
        "backup": {"required": False, "supported": bool(manifest.get("database", {}).get("backup_before_update", {}).get("entrypoint"))},
        "database_migration": {"required": False, "target_schema_version": manifest.get("database", {}).get("target_schema_version")},
        "verification_checks": _verification_checks(manifest),
    }


# --- Update planning ---


def prepare_update(engine, application_id: str, target_release_id: str) -> dict:
    with engine.connect() as conn:
        application_row = get_application_row(conn, application_id)
        target_release_row = get_release_row(conn, target_release_id)

    manifest = target_release_row["manifest"]
    blocking_issues = []

    source_release = None
    active_deployment_id = application_row["active_deployment_id"]
    if active_deployment_id:
        with engine.connect() as conn:
            active_deployment_row = conn.execute(
                deployments.select().where(deployments.c.deployment_id == active_deployment_id)
            ).mappings().first()
            source_release_row = conn.execute(
                releases.select().where(releases.c.release_id == active_deployment_row["release_id"])
            ).mappings().first()
        source_release = {"id": source_release_row["release_id"], "version": source_release_row["version"]}
    else:
        blocking_issues.append({"code": "PLT-TRANSITION-007", "message": "An active deployment is required before an update can be planned."})

    # Reuse PL4's already-tested transition decision rather than
    # re-implementing it — both must always agree on whether an update is
    # valid.
    if active_deployment_id:
        actions = get_available_actions(engine, application_id, target_release_id=target_release_id)
        update_action = next(a for a in actions["actions"] if a["action"] == "UPDATE")
        blocking_issues.extend(update_action["blocking_reasons"])

    preserved_values = _preserved_configuration(engine, active_deployment_id)
    preserved_secret_keys = _preserved_secret_keys(engine, active_deployment_id)
    configuration_inputs = _configuration_inputs(manifest, preserved_values, preserved_secret_keys)

    database = manifest.get("database", {})
    backup_decl = database.get("backup_before_update", {})
    migration_decl = database.get("migration", {})

    return {
        "plan_id": str(uuid.uuid4()),
        "operation_type": "UPDATE",
        "application": {"id": application_row["application_id"], "slug": application_row["slug"]},
        "source_release": source_release,
        "target_release": {"id": target_release_row["release_id"], "version": target_release_row["version"]},
        "allowed": not blocking_issues,
        "blocking_issues": blocking_issues,
        "canonical_path": manifest["deployment"]["canonical_path"],
        "compose_project_name": manifest["deployment"]["compose_project_name"],
        "configuration_inputs": configuration_inputs,
        "expected_services": _expected_services(manifest),
        "backup": {"required": bool(backup_decl.get("required", False)), "supported": bool(backup_decl.get("entrypoint"))},
        "database_migration": {
            "required": bool(migration_decl.get("required_for_update", False)),
            "target_schema_version": database.get("target_schema_version"),
        },
        "verification_checks": _verification_checks(manifest),
    }


# --- Input validation ---


def _validate_type(value, declared_type: str) -> str | None:
    """Returns an error message, or None if the value is well-formed for
    the declared type. Deliberately real for the common types
    (integer/boolean/port/ip_address/url); string-shaped types
    (string/path/hostname/password/choice) only require a string, since
    the Contract doesn't declare a stricter grammar for them.
    """
    if declared_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return "must be an integer"
    elif declared_type == "boolean":
        if not isinstance(value, bool):
            return "must be a boolean"
    elif declared_type == "port":
        if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= 65535):
            return "must be an integer between 1 and 65535"
    elif declared_type == "ip_address":
        try:
            ipaddress.ip_address(str(value))
        except ValueError:
            return "must be a valid IP address"
    elif declared_type == "url":
        parsed = urlparse(str(value))
        if not parsed.scheme or not parsed.netloc:
            return "must be a valid URL"
    else:
        if not isinstance(value, str):
            return f"must be a string ({declared_type})"
    return None


def validate_deployment_inputs(engine, release_id: str, configuration: dict) -> dict:
    with engine.connect() as conn:
        release_row = get_release_row(conn, release_id)

    declared = {decl["key"]: decl for decl in release_row["manifest"]["configuration"]["inputs"]}
    errors = []

    for key in configuration:
        if key not in declared:
            errors.append({"code": "PLT-INPUT-004", "key": key, "message": "Unknown configuration key."})

    for key, decl in declared.items():
        if not decl["required"]:
            continue
        if decl["source"] in ("generated", "platform"):
            continue
        if key not in configuration or "value" not in configuration[key]:
            errors.append({"code": "PLT-INPUT-002", "key": key, "message": "Missing required field."})

    for key, submitted in configuration.items():
        if key not in declared:
            continue
        decl = declared[key]
        value = submitted.get("value")
        if value is None:
            continue
        type_error = _validate_type(value, decl["type"])
        if type_error:
            errors.append({"code": "PLT-INPUT-003", "key": key, "message": f"Invalid value for '{key}': {type_error}."})
        if decl["type"] == "port" and type_error is None and not _port_is_available(value):
            errors.append({"code": "PLT-CONFIG-004", "key": key, "message": f"Port {value} is not currently available."})

    return {"valid": not errors, "errors": errors}
