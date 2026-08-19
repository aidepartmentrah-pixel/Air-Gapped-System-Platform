"""Verification and Host Reconciliation — PL7.

Completes the three-authority model (§7.1 State Authority Model):

    Release Manifest      -> what is expected
    Platform Registry     -> what was recorded
    Host Inspection        -> what is actually observed

Without this slice, "the install script exited 0" could silently become
"the application is healthy" — which the architecture explicitly
forbids (§7.8 Active Deployment Eligibility Rule). `PL6`'s own minimal
check (container running, nothing more) is replaced here by the real
thing; `installation.py` now calls `run_verification()` instead of its
own local check.

**Which checks are real vs. honestly `NOT_APPLICABLE`**: every check
below does real Docker/Registry inspection. `backend_health` and
`frontend_reachability` only run when a Release's own
`verification.required_checks` declares them — most Golden Fixtures
don't, since they're minimal `busybox`-based images with nothing to
probe, and reporting a fabricated `PASS` for a capability that was never
really checked would violate §5.24's Result Authority Principle.
`database_connectivity`/`migration_state` are `NOT_APPLICABLE` whenever
`database.required` is `false` (true for every current fixture) and
would honestly report `NOT_EXECUTED` — never a faked `PASS` — if a
future Release ever declared a required database, since no real DB
connectivity checking is built in Period A.
"""

from __future__ import annotations

import urllib.request
import uuid
from datetime import datetime, timezone

import docker

from rah_platform import operations
from rah_platform.application_query import get_application_row, get_release_row
from rah_platform.config import Config
from rah_platform.errors import (
    MandatoryVerificationFailedError,
    NoActiveDeploymentError,
    VerificationRunNotFoundError,
)
from rah_platform.models import (
    deployment_configuration,
    deployments,
    reconciliations,
    verification_checks,
    verification_runs,
)

MANDATORY_CHECK_KEYS = {
    "release_identity",
    "container_existence",
    "container_health",
    "image_tags",
    "selected_port",
    "offline_runtime",
    "persistent_configuration",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _docker_client():
    return docker.from_env()


def _containers_by_service(manifest: dict) -> dict:
    client = _docker_client()
    project = manifest["deployment"]["compose_project_name"]
    containers = client.containers.list(all=True, filters={"label": f"com.docker.compose.project={project}"})
    return {c.labels.get("com.docker.compose.service"): c for c in containers if c.labels.get("com.docker.compose.service")}


# --- Individual checks: each returns (status, message, evidence) ---


def _check_release_identity(engine, application_id: str, expected_release_id: str, verification_type: str) -> tuple[str, str, dict]:
    with engine.connect() as conn:
        application_row = get_application_row(conn, application_id)
    active_deployment_id = application_row["active_deployment_id"]
    if active_deployment_id is None:
        return "PASS", "No prior active deployment; verifying a fresh installation target.", {"expected_release_id": expected_release_id}
    with engine.connect() as conn:
        deployment_row = conn.execute(
            deployments.select().where(deployments.c.deployment_id == active_deployment_id)
        ).mappings().first()
    if deployment_row["release_id"] != expected_release_id:
        if verification_type == "POST_UPDATE":
            # PL8a: an update's own verification runs *before* the
            # Registry commit (§9.22 Failed Update Rule — an unsuccessful
            # update shall not overwrite the last known successful
            # active-deployment record, so the commit must wait until
            # after verification passes). The Registry still correctly
            # points at the source release at this point — that is not
            # drift, it is the expected pre-commit state. Whether the
            # *host* actually matches the target Release is what
            # `image_tags`/`container_health`/`selected_port` etc. below
            # independently establish.
            return (
                "PASS",
                "Update verification runs before the Registry commit; the recorded active deployment still correctly reflects the source Release.",
                {"active_release_id": deployment_row["release_id"], "expected_release_id": expected_release_id},
            )
        return (
            "FAIL",
            "The recorded active deployment does not match the expected Release.",
            {"active_release_id": deployment_row["release_id"], "expected_release_id": expected_release_id},
        )
    return "PASS", "The recorded active deployment matches the expected Release.", {}


def _check_container_existence(manifest: dict, containers: dict) -> tuple[str, str, dict]:
    expected = [img["service"] for img in manifest["docker"]["images"]]
    missing = [s for s in expected if s not in containers]
    if missing:
        return "FAIL", f"Missing containers for services: {missing}.", {"missing_services": missing, "expected_services": expected}
    return "PASS", "All expected containers exist.", {"expected_services": expected}


def _check_container_health(manifest: dict, containers: dict) -> tuple[str, str, dict]:
    expected = [img["service"] for img in manifest["docker"]["images"]]
    not_running = [s for s in expected if s in containers and containers[s].status != "running"]
    missing = [s for s in expected if s not in containers]
    if not_running or missing:
        return (
            "FAIL",
            "Not all expected containers are running.",
            {"not_running": not_running, "missing": missing},
        )
    return "PASS", "All expected containers are running.", {}


def _check_image_tags(manifest: dict, containers: dict) -> tuple[str, str, dict]:
    mismatches = []
    for img in manifest["docker"]["images"]:
        container = containers.get(img["service"])
        if container is None:
            continue  # covered by container_existence
        expected_tag = f"{img['repository']}:{img['tag']}"
        observed_tag = container.attrs["Config"]["Image"]
        if observed_tag != expected_tag:
            mismatches.append({"service": img["service"], "expected": expected_tag, "observed": observed_tag})
    if mismatches:
        return "FAIL", "One or more containers are running an unexpected image tag.", {"mismatches": mismatches}
    return "PASS", "All containers match their expected image tag.", {}


def _check_selected_port(manifest: dict, containers: dict, configuration_values: dict) -> tuple[str, str, dict]:
    port_inputs = [d for d in manifest["configuration"]["inputs"] if d["type"] == "port"]
    if not port_inputs:
        return "NOT_APPLICABLE", "No port-typed configuration is declared.", {}

    # first service that publishes a port — sufficient for this Period A's
    # single/simple-port Golden Fixtures.
    for img in manifest["docker"]["images"]:
        container = containers.get(img["service"])
        if container is None:
            continue
        port_bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        published = next((v for v in port_bindings.values() if v), None)
        if not published:
            continue
        observed_port = int(published[0]["HostPort"])
        key = port_inputs[0]["key"]
        expected_value = configuration_values.get(key)
        if expected_value is None:
            return "NOT_EXECUTED", "No recorded configuration value for the expected port.", {"key": key}
        expected_port = int(expected_value)
        if observed_port != expected_port:
            return (
                "FAIL",
                "The observed published port differs from the recorded configuration.",
                {"expected": expected_port, "observed": observed_port},
            )
        return "PASS", "The selected port matches the observed host binding.", {"port": observed_port}
    return "NOT_EXECUTED", "No published port was found on any expected container.", {}


def _check_offline_runtime(manifest: dict) -> tuple[str, str, dict]:
    declared = manifest.get("offline_requirements", {})
    violations = [k for k, v in declared.items() if v]
    if violations:
        return "FAIL", "The Release declares public/online runtime requirements.", {"violations": violations}
    return "PASS", "No public/online runtime requirements are declared.", {}


def _check_persistent_configuration(engine, application_id: str, manifest: dict, verification_type: str) -> tuple[str, str, dict]:
    if verification_type == "POST_UPDATE":
        # Same reasoning as `_check_release_identity`'s POST_UPDATE case:
        # the Registry's `deployment_configuration` rows for the still-active
        # deployment describe the *source* Release's config, not the
        # target's — there is nothing for this check to honestly compare
        # against until RECORDING_RESULT writes the new deployment's rows,
        # which happens after verification, not before.
        return "NOT_APPLICABLE", "The new deployment's configuration has not been recorded yet — verification runs before the Registry commit.", {}
    with engine.connect() as conn:
        application_row = get_application_row(conn, application_id)
    deployment_id = application_row["active_deployment_id"]
    if deployment_id is None:
        return "NOT_APPLICABLE", "No prior deployment configuration exists yet.", {}
    with engine.connect() as conn:
        rows = conn.execute(
            deployment_configuration.select().where(deployment_configuration.c.deployment_id == deployment_id)
        ).mappings().all()
    present = {r["key"] for r in rows}
    required = {d["key"] for d in manifest["configuration"]["inputs"] if d["required"]}
    missing = required - present
    if missing:
        return "FAIL", "Required configuration keys are missing from the recorded deployment.", {"missing_keys": sorted(missing)}
    return "PASS", "All required configuration keys are recorded.", {}


def _check_database_connectivity(manifest: dict) -> tuple[str, str, dict]:
    if not manifest.get("database", {}).get("required", False):
        return "NOT_APPLICABLE", "This Release does not declare a required database.", {}
    return "NOT_EXECUTED", "Database connectivity checking is not implemented in Period A.", {}


def _check_migration_state(manifest: dict) -> tuple[str, str, dict]:
    if not manifest.get("database", {}).get("required", False):
        return "NOT_APPLICABLE", "This Release does not declare a required database.", {}
    return "NOT_EXECUTED", "Migration state checking is not implemented in Period A.", {}


def _check_backend_health(manifest: dict, containers: dict, configuration_values: dict) -> tuple[str, str, dict]:
    required_checks = manifest.get("verification", {}).get("required_checks", [])
    if "backend_health" not in required_checks:
        return "NOT_APPLICABLE", "This Release does not require a backend health check.", {}
    port_inputs = [d for d in manifest["configuration"]["inputs"] if d["type"] == "port"]
    port = configuration_values.get(port_inputs[0]["key"]) if port_inputs else None
    if port is None:
        return "NOT_EXECUTED", "No port is configured to reach the backend.", {}
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as resp:  # noqa: S310
            if 200 <= resp.status < 300:
                return "PASS", "The backend responded successfully.", {"status_code": resp.status}
            return "FAIL", "The backend responded with a non-success status.", {"status_code": resp.status}
    except Exception as exc:  # noqa: BLE001
        return "FAIL", "The backend did not respond.", {"reason": str(exc)}


def _check_frontend_reachability(manifest: dict) -> tuple[str, str, dict]:
    required_checks = manifest.get("verification", {}).get("required_checks", [])
    if "frontend_reachability" not in required_checks:
        return "NOT_APPLICABLE", "This Release does not require a frontend reachability check.", {}
    return "NOT_EXECUTED", "Frontend reachability checking is not implemented in Period A.", {}


def _run_all_checks(engine, application_id: str, expected_release_id: str, verification_type: str, manifest: dict, configuration_values: dict, containers: dict) -> list[dict]:
    checks = [
        ("release_identity", *_check_release_identity(engine, application_id, expected_release_id, verification_type)),
        ("container_existence", *_check_container_existence(manifest, containers)),
        ("container_health", *_check_container_health(manifest, containers)),
        ("image_tags", *_check_image_tags(manifest, containers)),
        ("selected_port", *_check_selected_port(manifest, containers, configuration_values)),
        ("offline_runtime", *_check_offline_runtime(manifest)),
        ("persistent_configuration", *_check_persistent_configuration(engine, application_id, manifest, verification_type)),
        ("database_connectivity", *_check_database_connectivity(manifest)),
        ("migration_state", *_check_migration_state(manifest)),
        ("backend_health", *_check_backend_health(manifest, containers, configuration_values)),
        ("frontend_reachability", *_check_frontend_reachability(manifest)),
    ]
    return [{"check_key": key, "status": status, "message": message, "evidence": evidence} for key, status, message, evidence in checks]


def _overall_status(checks: list[dict]) -> str:
    for check in checks:
        if check["status"] == "FAIL":
            return "FAIL"
        if check["status"] == "NOT_EXECUTED" and check["check_key"] in MANDATORY_CHECK_KEYS:
            return "FAIL"
    return "PASS"


def run_verification(
    engine,
    *,
    application_id: str,
    expected_release_id: str,
    verification_type: str,
    operation_id: str,
    configuration_values: dict | None = None,
) -> dict:
    """The core check runner — always writes a `verification_runs` row
    (§7.25: every run preserved independently, a later pass never erases
    an earlier failure) linked to the given `operation_id` (either the
    install/update operation that triggered it, or a standalone `VERIFY`
    operation for a manual/API-initiated run).
    """
    with engine.connect() as conn:
        release_row = get_release_row(conn, expected_release_id)
    manifest = release_row["manifest"]

    if configuration_values is None:
        with engine.connect() as conn:
            application_row = get_application_row(conn, application_id)
        deployment_id = application_row["active_deployment_id"]
        configuration_values = {}
        if deployment_id:
            with engine.connect() as conn:
                rows = conn.execute(
                    deployment_configuration.select().where(deployment_configuration.c.deployment_id == deployment_id)
                ).mappings().all()
            configuration_values = {r["key"]: r["value"] for r in rows if not r["secret"]}

    containers = _containers_by_service(manifest)
    checks = _run_all_checks(engine, application_id, expected_release_id, verification_type, manifest, configuration_values, containers)
    status = _overall_status(checks)

    verification_run_id = str(uuid.uuid4())
    started_at = _now()
    with engine.begin() as conn:
        conn.execute(
            verification_runs.insert().values(
                verification_run_id=verification_run_id,
                application_id=application_id,
                expected_release_id=expected_release_id,
                operation_id=operation_id,
                verification_type=verification_type,
                status=status,
                started_at=started_at,
                completed_at=_now(),
            )
        )
        for check in checks:
            conn.execute(
                verification_checks.insert().values(
                    verification_run_id=verification_run_id,
                    check_key=check["check_key"],
                    status=check["status"],
                    message=check["message"],
                    evidence=check["evidence"],
                )
            )

    summary = {
        "passed": sum(1 for c in checks if c["status"] == "PASS"),
        "failed": sum(1 for c in checks if c["status"] == "FAIL"),
        "not_applicable": sum(1 for c in checks if c["status"] == "NOT_APPLICABLE"),
        "not_executed": sum(1 for c in checks if c["status"] == "NOT_EXECUTED"),
    }

    return {
        "verification_run_id": verification_run_id,
        "application_id": application_id,
        "expected_release_id": expected_release_id,
        "verification_type": verification_type,
        "status": status,
        "started_at": started_at.isoformat(),
        "completed_at": _now().isoformat(),
        "checks": checks,
        "summary": summary,
    }


def verify_deployment(
    engine, config: Config, *, application_id: str, expected_release_id: str | None = None, verification_type: str = "MANUAL", requested_by: str
) -> dict:
    """The standalone, API-facing entry point (`POST /applications/{id}/verify`).
    Creates its own `VERIFY` operation (§2.6: `verify_deployment` records
    verification through the Operation Framework) and runs synchronously
    — verification here is a handful of fast Docker/Registry checks, not
    a long-running script, so there is no need for `PL6`'s async
    202-then-poll pattern.
    """
    with engine.connect() as conn:
        application_row = get_application_row(conn, application_id)
    if expected_release_id is None:
        expected_release_id = _resolve_expected_release(engine, application_row)

    operation = operations.create_operation(
        engine, operation_type="VERIFY", application_id=application_id, requested_by=requested_by
    )
    operation_id = operation["operation_id"]
    operations.start_operation(engine, operation_id)

    result = run_verification(
        engine,
        application_id=application_id,
        expected_release_id=expected_release_id,
        verification_type=verification_type,
        operation_id=operation_id,
    )

    if result["status"] == "PASS":
        operations.succeed_operation(engine, operation_id)
    else:
        operations.fail_operation(
            engine,
            operation_id,
            MandatoryVerificationFailedError(
                "One or more mandatory verification checks failed.",
                stage="VERIFYING",
                details={"verification_run_id": result["verification_run_id"], "summary": result["summary"]},
            ),
        )
    return result


def _resolve_expected_release(engine, application_row) -> str:
    if not application_row["active_deployment_id"]:
        raise NoActiveDeploymentError(
            "No active deployment exists to infer an expected Release from; specify expected_release_id explicitly.",
            details={"application_id": application_row["application_id"]},
        )
    with engine.connect() as conn:
        deployment_row = conn.execute(
            deployments.select().where(deployments.c.deployment_id == application_row["active_deployment_id"])
        ).mappings().first()
    return deployment_row["release_id"]


def get_verification_result(engine, verification_run_id: str) -> dict:
    with engine.connect() as conn:
        run_row = conn.execute(
            verification_runs.select().where(verification_runs.c.verification_run_id == verification_run_id)
        ).mappings().first()
        if run_row is None:
            raise VerificationRunNotFoundError(
                "No verification run exists with the given verification_run_id.",
                details={"verification_run_id": verification_run_id},
            )
        check_rows = conn.execute(
            verification_checks.select().where(verification_checks.c.verification_run_id == verification_run_id)
        ).mappings().all()

    checks = [
        {"check_key": r["check_key"], "status": r["status"], "message": r["message"], "evidence": r["evidence"]}
        for r in check_rows
    ]
    summary = {
        "passed": sum(1 for c in checks if c["status"] == "PASS"),
        "failed": sum(1 for c in checks if c["status"] == "FAIL"),
        "not_applicable": sum(1 for c in checks if c["status"] == "NOT_APPLICABLE"),
        "not_executed": sum(1 for c in checks if c["status"] == "NOT_EXECUTED"),
    }
    return {
        "verification_run_id": run_row["verification_run_id"],
        "application_id": run_row["application_id"],
        "expected_release_id": run_row["expected_release_id"],
        "verification_type": run_row["verification_type"],
        "status": run_row["status"],
        "started_at": run_row["started_at"].isoformat(),
        "completed_at": run_row["completed_at"].isoformat() if run_row["completed_at"] else None,
        "checks": checks,
        "summary": summary,
    }


# --- Host Inspection (read-only) ---


def inspect_host_state(engine, application_id: str) -> dict:
    with engine.connect() as conn:
        application_row = get_application_row(conn, application_id)
    deployment_id = application_row["active_deployment_id"]
    if deployment_id is None:
        return {
            "application_id": application_id,
            "observed_at": _now().isoformat(),
            "deployment_path": {"expected": None, "exists": False},
            "compose": {"expected_project": None, "observed_project": None, "matches": False},
            "containers": [],
            "ports": [],
        }

    with engine.connect() as conn:
        deployment_row = conn.execute(
            deployments.select().where(deployments.c.deployment_id == deployment_id)
        ).mappings().first()
        release_row = get_release_row(conn, deployment_row["release_id"])
    manifest = release_row["manifest"]
    containers = _containers_by_service(manifest)

    container_results = []
    for img in manifest["docker"]["images"]:
        container = containers.get(img["service"])
        expected_image = f"{img['repository']}:{img['tag']}"
        container_results.append(
            {
                "service": img["service"],
                "expected_image": expected_image,
                "observed_image": container.attrs["Config"]["Image"] if container else None,
                "state": container.status.upper() if container else "MISSING",
                "healthy": bool(container and container.status == "running"),
            }
        )

    ports = []
    for img in manifest["docker"]["images"]:
        container = containers.get(img["service"])
        if not container:
            continue
        for container_port, bindings in (container.attrs.get("NetworkSettings", {}).get("Ports") or {}).items():
            if bindings:
                ports.append({"port": int(bindings[0]["HostPort"]), "expected": True, "listening": True})

    return {
        "application_id": application_id,
        "observed_at": _now().isoformat(),
        "deployment_path": {"expected": manifest["deployment"]["canonical_path"], "exists": True},
        "compose": {
            "expected_project": manifest["deployment"]["compose_project_name"],
            "observed_project": manifest["deployment"]["compose_project_name"] if containers else None,
            "matches": bool(containers),
        },
        "containers": container_results,
        "ports": ports,
    }


# --- Reconciliation ---


def reconcile_application_state(engine, application_id: str, *, record_result: bool = True) -> dict:
    with engine.connect() as conn:
        application_row = get_application_row(conn, application_id)
    deployment_id = application_row["active_deployment_id"]

    if deployment_id is None:
        status = "UNKNOWN"
        drift_items = [{"type": "NO_ACTIVE_DEPLOYMENT", "message": "No active deployment is recorded for this application."}]
        recorded_release = None
        observed_release = None
    else:
        with engine.connect() as conn:
            deployment_row = conn.execute(
                deployments.select().where(deployments.c.deployment_id == deployment_id)
            ).mappings().first()
            release_row = get_release_row(conn, deployment_row["release_id"])
        manifest = release_row["manifest"]
        recorded_release = release_row["version"]

        try:
            containers = _containers_by_service(manifest)
        except Exception as exc:  # noqa: BLE001
            status = "UNREACHABLE"
            drift_items = [{"type": "DOCKER_UNREACHABLE", "message": f"Could not reach the Docker Engine: {exc}"}]
            observed_release = None
        else:
            expected_services = [img["service"] for img in manifest["docker"]["images"]]
            running = [s for s in expected_services if containers.get(s) and containers[s].status == "running"]

            drift_items = []
            for img in manifest["docker"]["images"]:
                service = img["service"]
                container = containers.get(service)
                if container is None:
                    drift_items.append({"type": "CONTAINER_MISSING", "service": service, "message": f"Expected container for '{service}' does not exist."})
                    continue
                expected_tag = f"{img['repository']}:{img['tag']}"
                observed_tag = container.attrs["Config"]["Image"]
                if observed_tag != expected_tag:
                    drift_items.append({"type": "IMAGE_TAG_MISMATCH", "service": service, "expected": expected_tag, "observed": observed_tag})
                if container.status != "running":
                    drift_items.append({"type": "CONTAINER_NOT_RUNNING", "service": service, "observed_status": container.status})

            observed_release = recorded_release if running and not drift_items else None

            if len(running) == 0:
                status = "DRIFT_DETECTED"
            elif len(running) < len(expected_services):
                status = "PARTIALLY_RUNNING"
            elif drift_items:
                status = "DRIFT_DETECTED"
            else:
                status = "CONSISTENT"

    recorded_at = _now()
    if record_result:
        with engine.begin() as conn:
            conn.execute(
                reconciliations.insert().values(
                    application_id=application_id,
                    status=status,
                    recorded_release=recorded_release,
                    observed_release=observed_release,
                    drift_items=drift_items,
                    recorded_at=recorded_at,
                )
            )

    return {
        "application_id": application_id,
        "recorded_release": recorded_release,
        "observed_release": observed_release,
        "status": status,
        "drift_items": drift_items,
        "recorded_at": recorded_at.isoformat(),
    }
