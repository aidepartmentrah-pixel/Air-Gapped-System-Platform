"""Fresh Installation Execution — PL6.

The Platform's first complete deployment-changing operation, and the
first slice that actually modifies Debian/Docker state (§3.7
Installation Workflow). Deliberately scoped down per the plan's own
words: PL6 proves the *execution path* — request, lock, script, Docker,
Registry commit — with a minimal mandatory verification interface (real
Docker container inspection, not the Release's own `verify_deployment.sh`
script or any deep health probing). Full verification sophistication is
`PL7`'s job.

**Synchronous vs. asynchronous boundary**: everything through port
recheck and operation-lock acquisition happens synchronously in the
request path (§3.7 steps 1-4) — a caller gets an immediate rejection for
anything already known to be wrong. Once the operation is created and
`RUNNING`, actual execution (steps 5-19: prepare, run the script, verify,
commit) happens in a background thread, and the endpoint returns `202`
immediately with the operation snapshot — matching the architecture's own
long-running-operation model (§5.3) and the plan's own "Successful
Install" test wording ("202 Accepted → operation_id → RUNNING → ...").

**Deployment staging**: the canonical path (`deployment.canonical_path`
from the manifest, e.g. `/opt/rah/apps/<slug>`) is staged *inside the
Platform backend's own container filesystem* under
`config.deployments_path`, not a real host-mounted directory — a
deliberate Period A simplification (see Decisions Made in the Slicing
Task Table), sufficient to prove the execution mechanics without solving
host-persistent deployment-directory topology, which is out of this
slice's scope.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone

import docker

from rah_platform import deployment_planning, operations
from rah_platform.application_query import get_application_row, get_release_row, get_storage_state
from rah_platform.config import Config
from rah_platform.errors import (
    ActiveDeploymentCommitFailedError,
    ApplicationAlreadyInstalledError,
    DeploymentConfigurationInvalidError,
    FreshInstallUnsupportedError,
    InstallationScriptFailedError,
    InstallationScriptMissingError,
    InternalError,
    MandatoryVerificationFailedError,
    PlatformError,
    PortUnavailableError,
    ReleaseNotAvailableError,
    ScriptTimedOutError,
)
from rah_platform.models import applications, deployment_configuration, deployments, release_storage


def _now() -> datetime:
    return datetime.now(timezone.utc)


def install_application(engine, config: Config, *, release_id: str, configuration: dict, requested_by: str) -> dict:
    """Synchronous pre-checks and lock acquisition. Returns the operation
    snapshot immediately (the `202`-equivalent result) — execution
    continues in the background.
    """
    with engine.connect() as conn:
        release_row = get_release_row(conn, release_id)
        application_row = get_application_row(conn, release_row["application_id"])
        release_storage_state = get_storage_state(conn, release_row)

    manifest = release_row["manifest"]
    application_id = application_row["application_id"]

    if release_storage_state != "AVAILABLE":
        raise ReleaseNotAvailableError(
            "The selected Release Package is not available.",
            stage="VALIDATING",
            details={"release_id": release_id, "storage_state": release_storage_state},
        )
    if application_row["active_deployment_id"]:
        raise ApplicationAlreadyInstalledError(
            "The application is already installed.",
            stage="VALIDATING",
            details={"application_id": application_id},
        )
    if not manifest["deployment"]["supported_operations"].get("fresh_install", False):
        raise FreshInstallUnsupportedError(
            "Fresh installation is not supported by this Release.",
            stage="VALIDATING",
            details={"release_id": release_id},
        )

    validation = deployment_planning.validate_deployment_inputs(engine, release_id, configuration)
    if not validation["valid"]:
        raise DeploymentConfigurationInvalidError(
            "The supplied deployment configuration is invalid.",
            stage="VALIDATING",
            details={"errors": validation["errors"]},
        )

    # Recheck ports immediately before execution (§3.7 step 3, §7.17) —
    # real, live, synchronous, independent of validate_deployment_inputs'
    # own port check (this is the *last* check before the lock).
    for decl in manifest["configuration"]["inputs"]:
        if decl["type"] != "port":
            continue
        value = (configuration.get(decl["key"]) or {}).get("value")
        if value is not None and not deployment_planning.port_is_available(value):
            raise PortUnavailableError(
                "The selected port is no longer available.",
                stage="VALIDATING",
                details={"key": decl["key"], "port": value},
            )

    operation = operations.create_operation(
        engine, operation_type="INSTALL", application_id=application_id, requested_by=requested_by
    )
    operation_id = operation["operation_id"]
    operations.start_operation(engine, operation_id)

    thread = threading.Thread(
        target=_execute_install,
        args=(engine, config, operation_id, application_id, release_row, configuration),
        daemon=True,
    )
    thread.start()

    return operations.get_operation(engine, operation_id)


def _prepare_deployment_directory(config: Config, release_directory_name: str, slug: str) -> str:
    source = os.path.join(config.release_storage_path, release_directory_name)
    canonical_path = os.path.join(config.deployments_path, slug)
    if os.path.isdir(canonical_path):
        shutil.rmtree(canonical_path)
    os.makedirs(canonical_path, exist_ok=True)
    for sub in ("compose", "scripts", "docker-images", "configuration"):
        src = os.path.join(source, sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(canonical_path, sub))
    return canonical_path


def _render_configuration(canonical_path: str, manifest: dict, configuration: dict) -> None:
    """Writes `compose/.env` with resolved values — Docker Compose's own
    default env-file lookup, read by the install script's `docker
    compose up`. Secret values *are* written here (the running container
    legitimately needs them); what matters is that nothing in this
    function calls `operations.log`/`append_event`, so nothing here ever
    reaches operation history.
    """
    lines = []
    for decl in manifest["configuration"]["inputs"]:
        key = decl["key"]
        value = (configuration.get(key) or {}).get("value")
        if value is None:
            value = decl.get("default", "")
        lines.append(f"{key}={value}")
    env_path = os.path.join(canonical_path, "compose", ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _run_script(script_path: str, *, timeout_seconds: int) -> tuple[int | None, str, str]:
    try:
        result = subprocess.run(
            [script_path],
            cwd=os.path.dirname(script_path),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        return None, (exc.stdout or ""), (exc.stderr or "")


def _minimal_verify(manifest: dict) -> dict:
    """Real Docker inspection — not the Release's own verify script (that
    stays `PL7`'s job). Just: are the expected Compose services present
    and running, per the real Docker Engine.
    """
    client = docker.from_env()
    project = manifest["deployment"]["compose_project_name"]
    expected_services = {image["service"] for image in manifest["docker"]["images"]}
    containers = client.containers.list(filters={"label": f"com.docker.compose.project={project}"})
    running_services = {
        c.labels.get("com.docker.compose.service")
        for c in containers
        if c.status == "running" and c.labels.get("com.docker.compose.service")
    }
    missing = sorted(expected_services - running_services)
    return {
        "passed": not missing,
        "expected_services": sorted(expected_services),
        "running_services": sorted(running_services),
        "missing_services": missing,
    }


def _commit_deployment(engine, *, application_id: str, release_id: str, manifest: dict, configuration: dict, operation_id: str) -> str:
    deployment_id = str(uuid.uuid4())
    now = _now()
    try:
        with engine.begin() as conn:
            conn.execute(
                deployments.insert().values(
                    deployment_id=deployment_id,
                    application_id=application_id,
                    release_id=release_id,
                    operation_id=operation_id,
                    verification_status="PASS",
                    deployed_at=now,
                )
            )
            for decl in manifest["configuration"]["inputs"]:
                key = decl["key"]
                secret = bool(decl.get("secret", False))
                value = (configuration.get(key) or {}).get("value")
                conn.execute(
                    deployment_configuration.insert().values(
                        deployment_id=deployment_id,
                        key=key,
                        value=None if secret else (str(value) if value is not None else None),
                        secret=secret,
                        secret_reference=f"secret-ref:{key}" if secret else None,
                        source=decl["source"],
                    )
                )
            conn.execute(
                applications.update()
                .where(applications.c.application_id == application_id)
                .values(active_deployment_id=deployment_id)
            )
    except Exception as exc:
        raise ActiveDeploymentCommitFailedError(
            "The installation succeeded on the host but could not be committed to the Operational Registry.",
            stage="RECORDING_RESULT",
            details={"reconciliation_required": True, "reason": str(exc)},
        ) from exc
    return deployment_id


def _execute_install(engine, config: Config, operation_id: str, application_id: str, release_row, configuration: dict) -> None:
    manifest = release_row["manifest"]
    slug = manifest["application"]["slug"]
    try:
        with engine.connect() as conn:
            storage_row = conn.execute(
                release_storage.select().where(release_storage.c.release_id == release_row["release_id"])
            ).mappings().first()

        operations.update_stage(engine, operation_id, "PREPARING")
        canonical_path = _prepare_deployment_directory(config, storage_row["directory_name"], slug)
        _render_configuration(canonical_path, manifest, configuration)
        with engine.begin() as conn:
            operations.log(conn, operation_id, "Deployment directory prepared and configuration rendered.")

        operations.update_stage(engine, operation_id, "EXECUTING_SCRIPT")
        entrypoint = manifest["deployment"]["entrypoints"].get("install")
        script_path = os.path.join(canonical_path, "scripts", entrypoint) if entrypoint else None
        if not entrypoint or not os.path.isfile(script_path):
            raise InstallationScriptMissingError(
                "The declared install script does not exist.",
                stage="EXECUTING_SCRIPT",
                details={"entrypoint": entrypoint},
            )

        exit_code, stdout, stderr = _run_script(script_path, timeout_seconds=config.install_script_timeout_seconds)
        with engine.begin() as conn:
            operations.log(
                conn,
                operation_id,
                f"Install script exited with code {exit_code}." if exit_code is not None else "Install script timed out.",
                details={"exit_code": exit_code, "stderr_tail": (stderr or "")[-2000:]},
            )

        if exit_code is None:
            raise ScriptTimedOutError(
                "The install script did not complete within the configured timeout.",
                stage="EXECUTING_SCRIPT",
                details={"timeout_seconds": config.install_script_timeout_seconds},
            )
        if exit_code != 0:
            raise InstallationScriptFailedError(
                "The install script failed.",
                stage="EXECUTING_SCRIPT",
                details={"exit_code": exit_code, "stderr_tail": (stderr or "")[-2000:]},
            )

        operations.update_stage(engine, operation_id, "VERIFYING")
        verification = _minimal_verify(manifest)
        with engine.begin() as conn:
            operations.append_event(
                conn,
                operation_id,
                "VERIFICATION_COMPLETED",
                status="PASS" if verification["passed"] else "FAIL",
                message="Minimal installation verification.",
                details=verification,
            )
        if not verification["passed"]:
            raise MandatoryVerificationFailedError(
                "Required containers are not running.", stage="VERIFYING", details=verification
            )

        operations.update_stage(engine, operation_id, "RECORDING_RESULT")
        _commit_deployment(
            engine,
            application_id=application_id,
            release_id=release_row["release_id"],
            manifest=manifest,
            configuration=configuration,
            operation_id=operation_id,
        )

        operations.succeed_operation(engine, operation_id)
    except Exception as exc:
        error = exc if isinstance(exc, PlatformError) else InternalError(
            "Installation failed unexpectedly.", details={"reason": str(exc)}
        )
        operations.fail_operation(engine, operation_id, error)
