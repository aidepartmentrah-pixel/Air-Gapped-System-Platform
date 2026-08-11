"""Release Import and Registry — PL3.

Transforms a discovered candidate (`PL2`) into a trusted, immutable
Platform Release record. Per §3.5 (Release Import Workflow) and the
plan's own PL3 dev tasks, the Platform's own responsibility here is
narrower than the Packager Release Validator's full `RC-*` rule catalog
(`contracts/1.0/validation-rules.json`):

- **Re-validated directly by the Platform** (this module): Manifest
  schema (structural, against the real, mounted
  `release-manifest.schema.json`), the Release Contract version, the
  Compliance Report's `overall_result`, the checksum set, the Release
  fingerprint, architecture/Platform compatibility, and identity
  conflict.
- **Trusted, not re-verified**: everything the Compliance Report's
  `overall_result: PASS` already certifies (directory structure, script
  existence/executability, configuration/database/security rules, etc.)
  — §3.5 steps 6-7 read the report and require a successful result; they
  do not say the Platform re-runs the Packager's own Validator pipeline.

**Operation tracking**: failures that happen before the manifest can be
parsed and its `application.slug`/`release.version` trusted (missing/
unreadable manifest, unsupported schema/contract version, structural
schema failure) are not tied to an Operation — there is no reliable
application identity yet to attribute them to. From the point the
manifest is trusted onward (compliance, checksums, fingerprint,
compatibility, identity conflict, the registry write itself), every
attempt is tracked through the Generic Operation Framework (`PL1`), per
§7.12's Operation Attempt Rule.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import sqlalchemy as sa
import yaml
from sqlalchemy.exc import IntegrityError

from rah_platform import operations, release_discovery
from rah_platform.config import Config
from rah_platform.errors import (
    ChecksumFileMissingError,
    ChecksumMismatchError,
    ComplianceReportMissingError,
    ManifestSchemaInvalidError,
    PartialImportPreventedError,
    PlatformError,
    PlatformVersionTooOldError,
    ReleaseFingerprintMismatchError,
    ReleaseIdentityConflictError,
    ReleaseManifestMissingError,
    ReleaseManifestUnreadableError,
    ReleaseNotCompliantError,
    RequiredSharedServiceUnavailableError,
    UnsupportedArchitectureError,
    UnsupportedContractVersionError,
    UnsupportedManifestSchemaVersionError,
)
from rah_platform.models import applications, releases, release_storage

SUPPORTED_MANIFEST_SCHEMA_VERSIONS = {"1.0"}
SUPPORTED_CONTRACT_VERSIONS = {"1.0"}

_ARCH_ALIASES = {"x86_64": "amd64", "aarch64": "arm64"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_json_contract_file(config: Config, filename: str) -> dict:
    path = os.path.join(config.contracts_path, filename)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_and_validate_manifest(candidate_path: str, config: Config) -> dict:
    manifest_path = os.path.join(candidate_path, "release.yaml")
    if not os.path.isfile(manifest_path):
        raise ReleaseManifestMissingError(
            "release.yaml is missing from the candidate Release.",
            stage="VALIDATING",
            details={"candidate_path": candidate_path},
        )

    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ReleaseManifestUnreadableError(
            "release.yaml is not valid YAML.",
            stage="VALIDATING",
            details={"reason": str(exc)},
        ) from exc

    if not isinstance(manifest, dict):
        raise ReleaseManifestUnreadableError(
            "release.yaml did not parse to a mapping.", stage="VALIDATING"
        )

    schema_version = manifest.get("manifest_schema_version")
    if schema_version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        raise UnsupportedManifestSchemaVersionError(
            "This Platform does not support the declared manifest schema version.",
            stage="VALIDATING",
            details={
                "manifest_schema_version": schema_version,
                "supported": sorted(SUPPORTED_MANIFEST_SCHEMA_VERSIONS),
            },
        )

    contract_version = (manifest.get("compatibility") or {}).get("release_contract_version")
    if contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        raise UnsupportedContractVersionError(
            "This Platform does not support the declared Release Contract version.",
            stage="VALIDATING",
            details={
                "release_contract_version": contract_version,
                "supported": sorted(SUPPORTED_CONTRACT_VERSIONS),
            },
        )

    schema = _load_json_contract_file(config, "release-manifest.schema.json")
    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as exc:
        raise ManifestSchemaInvalidError(
            "release.yaml does not conform to the Release Manifest schema.",
            stage="VALIDATING",
            details={"reason": exc.message, "path": list(exc.absolute_path)},
        ) from exc

    return manifest


def _check_compliance_report(candidate_path: str, config: Config) -> dict:
    report_path = os.path.join(candidate_path, "compliance", "release-compliance-report.json")
    if not os.path.isfile(report_path):
        raise ComplianceReportMissingError(
            "No Compliance Report was found for this candidate Release.",
            stage="VALIDATING",
            details={"expected_path": report_path},
        )

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    schema = _load_json_contract_file(config, "compliance-report.schema.json")
    try:
        jsonschema.validate(report, schema)
    except jsonschema.ValidationError as exc:
        raise ComplianceReportMissingError(
            "The Compliance Report is not schema-valid and cannot be trusted.",
            stage="VALIDATING",
            details={"reason": exc.message},
        ) from exc

    if report.get("overall_result") != "PASS":
        raise ReleaseNotCompliantError(
            "The Compliance Report does not indicate successful compliance.",
            stage="VALIDATING",
            details={"overall_result": report.get("overall_result"), "summary": report.get("summary")},
        )

    return report


def _verify_checksums(candidate_path: str) -> None:
    checksums_path = os.path.join(candidate_path, "checksums", "SHA256SUMS")
    if not os.path.isfile(checksums_path):
        raise ChecksumFileMissingError(
            "checksums/SHA256SUMS is missing from the candidate Release.",
            stage="VALIDATING",
        )

    mismatches = []
    with open(checksums_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            expected_digest, _, rel_path = line.partition("  ")
            file_path = os.path.join(candidate_path, rel_path)
            if not os.path.isfile(file_path):
                mismatches.append({"path": rel_path, "reason": "file missing"})
                continue
            actual_digest = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
            if actual_digest != expected_digest:
                mismatches.append({"path": rel_path, "expected": expected_digest, "actual": actual_digest})

    if mismatches:
        raise ChecksumMismatchError(
            "One or more files do not match their recorded checksum.",
            stage="VALIDATING",
            details={"mismatches": mismatches},
        )


def _check_architecture_compatibility(manifest: dict) -> None:
    supported = manifest["compatibility"]["supported_architectures"]
    # os.uname().machine, not the stdlib `platform` module — this repo has
    # a top-level directory literally named `platform/`, which risks
    # shadowing the stdlib module for local (non-container) test runs.
    host_machine = os.uname().machine
    current = _ARCH_ALIASES.get(host_machine, host_machine)
    if current not in supported:
        raise UnsupportedArchitectureError(
            "This host's architecture is not supported by the Release.",
            stage="VALIDATING",
            details={"host_architecture": current, "supported_architectures": supported},
        )


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _check_platform_compatibility(manifest: dict, config: Config) -> None:
    minimum = manifest["compatibility"]["minimum_rah_oip_version"]
    if _version_tuple(config.platform_version) < _version_tuple(minimum):
        raise PlatformVersionTooOldError(
            "This Platform's version is older than the Release's minimum required version.",
            stage="VALIDATING",
            details={"platform_version": config.platform_version, "minimum_required": minimum},
        )


def _check_shared_services(manifest: dict) -> None:
    """No real shared-service inventory exists on the Platform yet — any
    *required* declared shared service is therefore honestly reported as
    unavailable rather than silently assumed present. None of PL3's Golden
    Fixtures declare one, so this never fires for them; it exists so a
    future Release that does declare one fails loudly instead of being
    silently accepted.
    """
    required = manifest["compatibility"].get("required_shared_services") or []
    missing = [s["id"] for s in required if s.get("required")]
    if missing:
        raise RequiredSharedServiceUnavailableError(
            "This Release requires shared services the Platform cannot currently verify.",
            stage="VALIDATING",
            details={"missing_services": missing},
        )


def _find_or_create_application(engine, *, slug: str, name: str) -> str:
    with engine.begin() as conn:
        existing = conn.execute(
            sa.select(applications.c.application_id).where(applications.c.slug == slug)
        ).scalar()
        if existing:
            return existing
        application_id = str(uuid.uuid4())
        conn.execute(
            applications.insert().values(
                application_id=application_id,
                slug=slug,
                name=name,
                description=None,
                created_at=_now(),
            )
        )
        return application_id


def _find_existing_release(engine, *, application_id: str, version: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            releases.select().where(
                releases.c.application_id == application_id, releases.c.version == version
            )
        ).mappings().first()
    return dict(row) if row else None


def _write_release_and_storage(engine, *, application_id, manifest, fingerprint, candidate, candidate_path) -> str:
    release_id = str(uuid.uuid4())
    now = _now()
    try:
        with engine.begin() as conn:
            conn.execute(
                releases.insert().values(
                    release_id=release_id,
                    application_id=application_id,
                    version=manifest["release"]["version"],
                    contract_version=manifest["compatibility"]["release_contract_version"],
                    manifest_schema_version=manifest["manifest_schema_version"],
                    fingerprint=fingerprint,
                    summary=manifest["release"].get("summary"),
                    manifest=manifest,
                    created_at_engineering=manifest["release"].get("created_at"),
                    imported_at=now,
                )
            )
            conn.execute(
                release_storage.insert().values(
                    release_id=release_id,
                    directory_name=candidate["directory_name"],
                    path=candidate_path,
                    state="AVAILABLE",
                    integrity_verified=True,
                    created_at=now,
                    updated_at=now,
                )
            )
    except IntegrityError as exc:
        raise PartialImportPreventedError(
            "The Release could not be committed to the Operational Registry.",
            stage="RECORDING_RESULT",
            details={"reason": str(exc)},
        ) from exc
    return release_id


def _mark_candidate_imported(engine, candidate_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            release_discovery.release_candidates.update()
            .where(release_discovery.release_candidates.c.candidate_id == candidate_id)
            .values(already_imported=True, discovery_state="ALREADY_IMPORTED")
        )


def _release_result(row: dict, *, application: dict, storage_state: str, storage_path: str, already_imported: bool = False) -> dict:
    return {
        "release_id": row["release_id"],
        "application": {"id": application["application_id"], "slug": application["slug"], "name": application["name"]},
        "release": {
            "version": row["version"],
            "contract_version": row["contract_version"],
            "manifest_schema_version": row["manifest_schema_version"],
            "fingerprint": row["fingerprint"],
            "summary": row["summary"],
        },
        "storage": {"state": storage_state, "path": storage_path, "integrity_verified": True},
        "imported_at": row["imported_at"].isoformat() if hasattr(row["imported_at"], "isoformat") else row["imported_at"],
        "already_imported": already_imported,
    }


def import_release(engine, config: Config, *, candidate_id: str, requested_by: str, expected_fingerprint: str | None = None) -> dict:
    candidate = release_discovery.get_candidate(engine, candidate_id)
    candidate_path = os.path.join(config.release_storage_path, candidate["directory_name"])

    # Steps before the manifest can be trusted: no application identity is
    # known yet, so no Operation is opened for these failures.
    manifest = _load_and_validate_manifest(candidate_path, config)

    slug = manifest["application"]["slug"]
    name = manifest["application"]["name"]
    version = manifest["release"]["version"]

    application_id = _find_or_create_application(engine, slug=slug, name=name)
    with engine.connect() as conn:
        application = dict(
            conn.execute(applications.select().where(applications.c.application_id == application_id)).mappings().first()
        )

    fingerprint = release_discovery.compute_fingerprint(candidate_path)

    existing = _find_existing_release(engine, application_id=application_id, version=version)
    if existing and existing["fingerprint"] == fingerprint:
        # Same Version / Same Fingerprint — predictable no-op, not tracked
        # as a new Operation since nothing changes.
        _mark_candidate_imported(engine, candidate_id)
        with engine.connect() as conn:
            storage_row = conn.execute(
                release_storage.select().where(release_storage.c.release_id == existing["release_id"])
            ).mappings().first()
        return _release_result(
            existing,
            application=application,
            storage_state=storage_row["state"],
            storage_path=storage_row["path"],
            already_imported=True,
        )

    operation = operations.create_operation(
        engine, operation_type="IMPORT", application_id=application_id, requested_by=requested_by
    )
    operation_id = operation["operation_id"]
    operations.start_operation(engine, operation_id)

    try:
        if existing and existing["fingerprint"] != fingerprint:
            raise ReleaseIdentityConflictError(
                "A Release with this application and version already exists with different content.",
                stage="VALIDATING",
                details={
                    "application_slug": slug,
                    "version": version,
                    "existing_fingerprint": existing["fingerprint"],
                    "incoming_fingerprint": fingerprint,
                },
            )

        _check_compliance_report(candidate_path, config)
        _verify_checksums(candidate_path)

        if expected_fingerprint and expected_fingerprint != fingerprint:
            raise ReleaseFingerprintMismatchError(
                "The computed Release fingerprint does not match the expected fingerprint.",
                stage="VALIDATING",
                details={"expected": expected_fingerprint, "computed": fingerprint},
            )

        _check_architecture_compatibility(manifest)
        _check_platform_compatibility(manifest, config)
        _check_shared_services(manifest)

        release_id = _write_release_and_storage(
            engine,
            application_id=application_id,
            manifest=manifest,
            fingerprint=fingerprint,
            candidate=candidate,
            candidate_path=candidate_path,
        )
    except Exception as exc:
        error = exc if isinstance(exc, PlatformError) else PartialImportPreventedError(
            "Import failed unexpectedly.", stage="RECORDING_RESULT", details={"reason": str(exc)}
        )
        operations.fail_operation(engine, operation_id, error)
        if error is exc:
            raise
        raise error from exc

    operations.succeed_operation(engine, operation_id)
    _mark_candidate_imported(engine, candidate_id)

    with engine.connect() as conn:
        release_row = dict(conn.execute(releases.select().where(releases.c.release_id == release_id)).mappings().first())
        storage_row = conn.execute(
            release_storage.select().where(release_storage.c.release_id == release_id)
        ).mappings().first()

    return _release_result(
        release_row,
        application=application,
        storage_state=storage_row["state"],
        storage_path=storage_row["path"],
    )
