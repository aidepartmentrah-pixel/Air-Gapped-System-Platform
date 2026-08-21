"""Update — PL8a (second half of Backup + Update; see `backup.py`'s own
module docstring for the `PL8a`/`PL8b` split rationale).

Proves the second major lifecycle transition (§3.8/§9.21):

    Existing application (active Release)
            ↓
    New Release, existing configuration/data preserved

**Sequencing, matching §9.19/§9.22/§9.26 exactly**: `BACKING_UP` (real,
mandatory-if-declared, shares this UPDATE operation's own `operation_id`
with the backup — architecture "Choose Implementation Mechanisms" doc
§7.5.5) → `EXECUTING_SCRIPT` (the target Release's own `entrypoints.update`
script, real subprocess, same primitive as `PL6`'s install) →
`MIGRATING` (if declared, real script + real captured exit code as
migration evidence — Period A does not implement a database-level
migration-*state* check, matching `PL7`'s own already-stated boundary for
`database_connectivity`/`migration_state`; migration evidence here is the
script's own real exit code, not a fabricated schema comparison) →
`VERIFYING` (reuses `PL7`'s `run_verification` wholesale, with
`verification_type="POST_UPDATE"` — required a real fix to two of
`verification.py`'s own checks, since an update's verification runs
*before* the Registry commit and the previous checks assumed the Registry
already agreed with what's being verified; see the Slicing Task Table's
PL8a amendment note to PL7) → `RECORDING_RESULT` (only reached after a
real `PASS` — §9.22 Failed Update Rule: "An unsuccessful update SHALL NOT
overwrite the last known successful active-deployment record").

**Configuration preservation is real, not just planned**: §7.16's
Secret-State Rule means the Operational Registry never stores a secret's
real plaintext, so a preserved secret's actual value is read back from
the *previous* deployment's real rendered `compose/.env`
(`installation.read_rendered_env`) before that directory is replaced —
never from the Registry, which only ever had `secret_reference`.

**Which Release's manifest declares `backup_before_update`/`migration`**:
the *target* (the Release being updated to), matching `PL5`'s
`prepare_update` — a documented Decision, not something the architecture
text disambiguates on its own; see the Slicing Task Table.
"""

from __future__ import annotations

import os
import threading

from rah_platform import application_query, backup, deployment_planning, operations, verification
from rah_platform.application_query import get_application_row, get_release_row
from rah_platform.config import Config
from rah_platform.errors import (
    ConfigurationPreservationFailedError,
    DeploymentConfigurationInvalidError,
    InternalError,
    MandatoryBackupFailedError,
    MigrationFailedError,
    PlatformError,
    PortUnavailableError,
    PostUpdateVerificationFailedError,
    ScriptTimedOutError,
    UpdatePrerequisitesFailedError,
    UpdateRecoveryRequiredError,
    UpdateScriptFailedError,
    UpdateScriptMissingError,
)
from rah_platform.installation import (
    commit_deployment,
    prepare_deployment_directory,
    read_rendered_env,
    render_configuration,
    run_script,
)
from rah_platform.models import deployments, release_storage


_TYPE_PLACEHOLDERS = {
    "integer": 1,
    "port": 1,
    "boolean": True,
    "ip_address": "127.0.0.1",
    "url": "http://localhost",
}


def _validate_update_configuration(
    engine, target_release_id: str, manifest: dict, overrides: dict, preserved_values: dict, preserved_secret_keys: set[str]
) -> dict:
    """Reuses `deployment_planning.validate_deployment_inputs` wholesale
    (both its presence *and* type checks) rather than reimplementing
    either — but every preserved value comes back out of the Registry as
    a plain string (`deployment_configuration.value` is `TEXT`), so
    handing that real string to a strict type check (e.g. `port` expects
    a real `int`) would always fail a field that was already valid when
    first submitted at install time. A required key already satisfied by
    preservation gets a type-correct *placeholder* instead — sufficient
    to pass "present and correctly typed," since the real preserved value
    is substituted at execution time, never here.
    """
    filled = {**overrides}
    for decl in manifest["configuration"]["inputs"]:
        key = decl["key"]
        if key in filled or (key not in preserved_values and key not in preserved_secret_keys):
            continue
        filled[key] = {"value": _TYPE_PLACEHOLDERS.get(decl["type"], "x")}
    return deployment_planning.validate_deployment_inputs(engine, target_release_id, filled)


def update_application(
    engine,
    config: Config,
    *,
    application_id: str,
    target_release_id: str,
    configuration_overrides: dict | None = None,
    create_backup: bool = True,
    requested_by: str,
) -> dict:
    """Synchronous pre-checks and lock acquisition, mirroring `PL6`'s
    `install_application` structure exactly. Returns the operation
    snapshot immediately (§6.22: `202 Accepted`) — execution continues in
    the background.
    """
    configuration_overrides = configuration_overrides or {}

    with engine.connect() as conn:
        target_release_row = get_release_row(conn, target_release_id)
        application_row = get_application_row(conn, application_id)

    actions = application_query.get_available_actions(engine, application_id, target_release_id=target_release_id)
    update_action = next(a for a in actions["actions"] if a["action"] == "UPDATE")
    if not update_action["allowed"]:
        raise UpdatePrerequisitesFailedError(
            "This update cannot proceed.",
            stage="VALIDATING",
            details={"blocking_reasons": update_action["blocking_reasons"]},
        )

    active_deployment_id = application_row["active_deployment_id"]
    with engine.connect() as conn:
        source_deployment_row = conn.execute(
            deployments.select().where(deployments.c.deployment_id == active_deployment_id)
        ).mappings().first()
        source_release_row = get_release_row(conn, source_deployment_row["release_id"])

    manifest = target_release_row["manifest"]
    preserved_values = deployment_planning.preserved_configuration(engine, active_deployment_id)
    preserved_secret_key_set = deployment_planning.preserved_secret_keys(engine, active_deployment_id)

    validation = _validate_update_configuration(
        engine, target_release_id, manifest, configuration_overrides, preserved_values, preserved_secret_key_set
    )
    if not validation["valid"]:
        raise DeploymentConfigurationInvalidError(
            "The supplied deployment configuration is invalid.",
            stage="VALIDATING",
            details={"errors": validation["errors"]},
        )

    # A live port recheck only makes sense for a port the caller is
    # actually *changing* — the preserved/current port is expected to be
    # in use by the very deployment this update is about to replace, so
    # checking it live before that replacement would always spuriously
    # fail.
    for decl in manifest["configuration"]["inputs"]:
        if decl["type"] != "port" or decl["key"] not in configuration_overrides:
            continue
        value = (configuration_overrides.get(decl["key"]) or {}).get("value")
        if value is not None and not deployment_planning.port_is_available(value):
            raise PortUnavailableError(
                "The selected port is no longer available.",
                stage="VALIDATING",
                details={"key": decl["key"], "port": value},
            )

    operation = operations.create_operation(
        engine, operation_type="UPDATE", application_id=application_id, requested_by=requested_by
    )
    operation_id = operation["operation_id"]
    operations.start_operation(engine, operation_id)

    thread = threading.Thread(
        target=_execute_update,
        args=(engine, config, operation_id, application_id, source_deployment_row, target_release_row, configuration_overrides, create_backup),
        daemon=True,
    )
    thread.start()

    return operations.get_operation(engine, operation_id)


def _execute_update(
    engine, config: Config, operation_id: str, application_id: str, source_deployment_row, target_release_row, configuration_overrides: dict, create_backup_flag: bool
) -> None:
    manifest = target_release_row["manifest"]
    slug = manifest["application"]["slug"]
    active_canonical_path = os.path.join(config.deployments_path, slug)
    source_deployment_id = source_deployment_row["deployment_id"]

    try:
        preserved_values = deployment_planning.preserved_configuration(engine, source_deployment_id)
        preserved_secret_key_set = deployment_planning.preserved_secret_keys(engine, source_deployment_id)

        operations.update_stage(engine, operation_id, "BACKING_UP")
        database = manifest.get("database", {})
        backup_decl = database.get("backup_before_update", {})
        backup_mandatory = bool(backup_decl.get("required", False))
        if backup_mandatory or create_backup_flag:
            try:
                backup.perform_backup(
                    engine,
                    config,
                    operation_id=operation_id,
                    application_id=application_id,
                    deployment_id=source_deployment_id,
                    release_row=target_release_row,
                    backup_type="DATABASE",
                    verify_after_creation=True,
                    active_canonical_path=active_canonical_path,
                )
            except PlatformError as exc:
                # §9.19: "If mandatory backup fails, the update shall
                # stop." Applied uniformly whether the backup was
                # mandatory-by-manifest or only requested by the caller
                # — a caller who explicitly asked for a backup should
                # not have the update silently proceed without one.
                raise MandatoryBackupFailedError(
                    "The pre-update backup failed; the update did not begin.",
                    stage="BACKING_UP",
                    details={"reason": exc.to_dict()},
                ) from exc

        # Real secret preservation (§7.16 Secret-State Rule: the Registry
        # never stored the plaintext) — must happen *before*
        # `prepare_deployment_directory` replaces the directory this
        # reads from.
        final_configuration = {**configuration_overrides}
        for key, value in preserved_values.items():
            final_configuration.setdefault(key, {"value": value})
        remaining_secret_keys = [k for k in preserved_secret_key_set if k not in final_configuration]
        if remaining_secret_keys:
            old_env = read_rendered_env(active_canonical_path)
            for key in remaining_secret_keys:
                real_value = old_env.get(key)
                if real_value is None:
                    raise ConfigurationPreservationFailedError(
                        "A preserved secret's real value could not be recovered from the previous deployment.",
                        stage="BACKING_UP",
                        details={"key": key},
                    )
                final_configuration[key] = {"value": real_value}

        operations.update_stage(engine, operation_id, "EXECUTING_SCRIPT")
        with engine.connect() as conn:
            storage_row = conn.execute(
                release_storage.select().where(release_storage.c.release_id == target_release_row["release_id"])
            ).mappings().first()
        canonical_path = prepare_deployment_directory(config, storage_row["directory_name"], slug)
        render_configuration(canonical_path, manifest, final_configuration)
        with engine.begin() as conn:
            operations.log(conn, operation_id, "Deployment directory replaced and configuration rendered for the target Release.")

        entrypoint = manifest["deployment"]["entrypoints"].get("update")
        # entrypoint is already a full path relative to the Release root (e.g. "scripts/update_offline.sh")
        script_path = os.path.join(canonical_path, entrypoint) if entrypoint else None
        if not entrypoint or not os.path.isfile(script_path):
            raise UpdateScriptMissingError(
                "The declared update script does not exist.",
                stage="EXECUTING_SCRIPT",
                details={"entrypoint": entrypoint},
            )

        exit_code, stdout, stderr = run_script(script_path, timeout_seconds=config.install_script_timeout_seconds)
        with engine.begin() as conn:
            operations.log(
                conn,
                operation_id,
                f"Update script exited with code {exit_code}." if exit_code is not None else "Update script timed out.",
                details={"exit_code": exit_code, "stderr_tail": (stderr or "")[-2000:]},
            )
        if exit_code is None:
            raise ScriptTimedOutError(
                "The update script did not complete within the configured timeout.",
                stage="EXECUTING_SCRIPT",
                details={"timeout_seconds": config.install_script_timeout_seconds},
            )
        if exit_code != 0:
            raise UpdateScriptFailedError(
                "The update script failed.",
                stage="EXECUTING_SCRIPT",
                details={"exit_code": exit_code, "stderr_tail": (stderr or "")[-2000:]},
            )

        migration_decl = database.get("migration", {})
        if migration_decl.get("required_for_update", False):
            operations.update_stage(engine, operation_id, "MIGRATING")
            migration_entrypoint = migration_decl.get("entrypoint")
            # migration_entrypoint is already a full path relative to the Release root
            migration_script_path = (
                os.path.join(canonical_path, migration_entrypoint) if migration_entrypoint else None
            )
            if not migration_entrypoint or not os.path.isfile(migration_script_path):
                raise MigrationFailedError(
                    "The declared migration script does not exist.",
                    stage="MIGRATING",
                    details={"entrypoint": migration_entrypoint},
                )
            migration_exit_code, migration_stdout, migration_stderr = run_script(
                migration_script_path, timeout_seconds=config.install_script_timeout_seconds
            )
            with engine.begin() as conn:
                operations.append_event(
                    conn,
                    operation_id,
                    "MIGRATION_COMPLETED",
                    status="PASS" if migration_exit_code == 0 else "FAIL",
                    message="Database migration executed." if migration_exit_code == 0 else "Database migration failed.",
                    details={
                        "exit_code": migration_exit_code,
                        "target_schema_version": database.get("target_schema_version"),
                        "stderr_tail": (migration_stderr or "")[-2000:],
                    },
                )
            if migration_exit_code != 0:
                raise MigrationFailedError(
                    "The database migration script failed.",
                    stage="MIGRATING",
                    details={"exit_code": migration_exit_code, "stderr_tail": (migration_stderr or "")[-2000:]},
                )

        operations.update_stage(engine, operation_id, "VERIFYING")
        configuration_values = {
            decl["key"]: str((final_configuration.get(decl["key"]) or {}).get("value", decl.get("default", "")))
            for decl in manifest["configuration"]["inputs"]
            if not decl.get("secret", False)
        }
        verification_result = verification.run_verification(
            engine,
            application_id=application_id,
            expected_release_id=target_release_row["release_id"],
            verification_type="POST_UPDATE",
            operation_id=operation_id,
            configuration_values=configuration_values,
        )
        with engine.begin() as conn:
            operations.append_event(
                conn,
                operation_id,
                "VERIFICATION_COMPLETED",
                status=verification_result["status"],
                message="Post-update verification.",
                details={"verification_run_id": verification_result["verification_run_id"], "summary": verification_result["summary"]},
            )
        if verification_result["status"] != "PASS":
            # §9.22 Failed Update Rule: the target does not become
            # active. The host may have genuinely changed (script and
            # migration both ran) — that is exactly what makes recovery
            # meaningful, `PL8b`'s job.
            raise PostUpdateVerificationFailedError(
                "One or more mandatory post-update verification checks failed.",
                stage="VERIFYING",
                details={"verification_run_id": verification_result["verification_run_id"], "summary": verification_result["summary"]},
            )

        operations.update_stage(engine, operation_id, "RECORDING_RESULT")
        try:
            commit_deployment(
                engine,
                application_id=application_id,
                release_id=target_release_row["release_id"],
                manifest=manifest,
                configuration=final_configuration,
                operation_id=operation_id,
            )
        except PlatformError as exc:
            raise UpdateRecoveryRequiredError(
                "The update succeeded on the host but could not be committed to the Operational Registry.",
                stage="RECORDING_RESULT",
                details={"recovery_required": True, "reason": exc.to_dict()},
            ) from exc

        operations.succeed_operation(engine, operation_id)
    except Exception as exc:
        error = exc if isinstance(exc, PlatformError) else InternalError(
            "Update failed unexpectedly.", details={"reason": str(exc)}
        )
        operations.fail_operation(engine, operation_id, error)
