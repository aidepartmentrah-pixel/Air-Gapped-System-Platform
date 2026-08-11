import shutil

import pytest

from conftest import CONTRACTS_PATH, FIXTURES_ROOT
from rah_platform import release_discovery, release_import
from rah_platform.config import Config
from rah_platform.errors import (
    ChecksumMismatchError,
    PartialImportPreventedError,
    PlatformVersionTooOldError,
    ReleaseIdentityConflictError,
    ReleaseNotCompliantError,
    UnsupportedArchitectureError,
    UnsupportedManifestSchemaVersionError,
)


def _config(tmp_path) -> Config:
    return Config(
        database_url="unused",
        release_storage_path=str(tmp_path),
        log_level="INFO",
        contracts_path=str(CONTRACTS_PATH),
    )


def _stage(tmp_path, *names: str) -> None:
    for name in names:
        shutil.copytree(FIXTURES_ROOT / name, tmp_path / name)


def _scan_and_get_candidate_id(db_engine, tmp_path, directory_name: str) -> str:
    result = release_discovery.scan_releases(db_engine, str(tmp_path))
    for candidate in result["candidates"]:
        if candidate["directory_name"] == directory_name:
            return candidate["candidate_id"]
    raise AssertionError(f"{directory_name} not found in scan result")


# --- First Release of New Application ---


def test_first_release_of_new_application_creates_application_and_release(db_engine, tmp_path):
    _stage(tmp_path, "valid-release-1.0.0")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "valid-release-1.0.0")

    result = release_import.import_release(
        db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
    )

    assert result["application"]["slug"] == "golden-test-app"
    assert result["release"]["version"] == "1.0.0"
    assert result["storage"]["state"] == "AVAILABLE"
    assert result["already_imported"] is False


# --- Second Release of Same Application ---


def test_second_release_of_same_application_adds_release_not_new_app(db_engine, tmp_path):
    _stage(tmp_path, "valid-release-1.0.0", "valid-release-1.1.0")
    c1 = _scan_and_get_candidate_id(db_engine, tmp_path, "valid-release-1.0.0")
    c2 = _scan_and_get_candidate_id(db_engine, tmp_path, "valid-release-1.1.0")

    r1 = release_import.import_release(db_engine, _config(tmp_path), candidate_id=c1, requested_by="operator:test")
    r2 = release_import.import_release(db_engine, _config(tmp_path), candidate_id=c2, requested_by="operator:test")

    assert r1["application"]["id"] == r2["application"]["id"]
    assert r1["release"]["version"] == "1.0.0"
    assert r2["release"]["version"] == "1.1.0"


# --- Invalid Checksum ---


def test_invalid_checksum_import_rejected(db_engine, tmp_path):
    _stage(tmp_path, "invalid-checksum")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "invalid-checksum")

    with pytest.raises(ChecksumMismatchError):
        release_import.import_release(
            db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
        )


# --- Failed Compliance Report ---


def test_failed_compliance_report_import_rejected(db_engine, tmp_path):
    _stage(tmp_path, "failed-compliance")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "failed-compliance")

    with pytest.raises(ReleaseNotCompliantError):
        release_import.import_release(
            db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
        )


# --- Unsupported Contract ---


def test_unsupported_contract_import_rejected(db_engine, tmp_path):
    _stage(tmp_path, "unsupported-contract")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "unsupported-contract")

    with pytest.raises(UnsupportedManifestSchemaVersionError) as exc_info:
        release_import.import_release(
            db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
        )
    assert exc_info.value.code == "PLT-CONTRACT-002"


# --- Same Version / Same Fingerprint ---


def test_same_version_same_fingerprint_is_predictable_noop(db_engine, tmp_path):
    _stage(tmp_path, "valid-release-1.0.0")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "valid-release-1.0.0")

    first = release_import.import_release(
        db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
    )
    second = release_import.import_release(
        db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
    )

    assert first["release_id"] == second["release_id"]
    assert second["already_imported"] is True


def test_same_version_same_fingerprint_does_not_duplicate_release_row(db_engine, tmp_path):
    import sqlalchemy as sa

    _stage(tmp_path, "valid-release-1.0.0")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "valid-release-1.0.0")

    release_import.import_release(db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test")
    release_import.import_release(db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test")

    with db_engine.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM releases")).scalar()
    assert count == 1


# --- Same Version / Different Fingerprint ---


def test_same_version_different_fingerprint_rejected_with_identity_conflict(db_engine, tmp_path):
    _stage(tmp_path, "valid-release-1.0.0", "identity-conflict")
    original_id = _scan_and_get_candidate_id(db_engine, tmp_path, "valid-release-1.0.0")
    conflicting_id = _scan_and_get_candidate_id(db_engine, tmp_path, "identity-conflict")

    release_import.import_release(
        db_engine, _config(tmp_path), candidate_id=original_id, requested_by="operator:test"
    )

    with pytest.raises(ReleaseIdentityConflictError) as exc_info:
        release_import.import_release(
            db_engine, _config(tmp_path), candidate_id=conflicting_id, requested_by="operator:test"
        )
    assert exc_info.value.code == "PLT-IMPORT-005"
    assert exc_info.value.http_status == 409


# --- Partial Registry Failure ---


def test_partial_registry_failure_leaves_no_partial_state(db_engine, tmp_path, monkeypatch):
    import sqlalchemy as sa

    _stage(tmp_path, "valid-release-1.0.0")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "valid-release-1.0.0")

    monkeypatch.setattr(
        "rah_platform.release_import.release_storage.insert",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated failure")),
    )

    with pytest.raises(PartialImportPreventedError):
        release_import.import_release(
            db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
        )

    with db_engine.connect() as conn:
        releases_count = conn.execute(sa.text("SELECT COUNT(*) FROM releases")).scalar()
        storage_count = conn.execute(sa.text("SELECT COUNT(*) FROM release_storage")).scalar()
    assert releases_count == 0
    assert storage_count == 0


def test_partial_registry_failure_operation_recorded_as_failed(db_engine, tmp_path, monkeypatch):
    _stage(tmp_path, "valid-release-1.0.0")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "valid-release-1.0.0")

    monkeypatch.setattr(
        "rah_platform.release_import.release_storage.insert",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated failure")),
    )

    with pytest.raises(PartialImportPreventedError):
        release_import.import_release(
            db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
        )

    from rah_platform import operations as ops_module
    import sqlalchemy as sa

    with db_engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT status FROM operations WHERE operation_type = 'IMPORT'")
        ).mappings().first()
    assert row["status"] == "FAILED"


# --- Architecture / Platform Compatibility (beyond the required 9, since this is real logic) ---


def test_wrong_architecture_import_rejected(db_engine, tmp_path):
    _stage(tmp_path, "wrong-architecture")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "wrong-architecture")

    with pytest.raises(UnsupportedArchitectureError) as exc_info:
        release_import.import_release(
            db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
        )
    assert exc_info.value.code == "PLT-COMPATIBILITY-001"


def test_platform_version_too_old_import_rejected(db_engine, tmp_path):
    _stage(tmp_path, "platform-version-too-old")
    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "platform-version-too-old")

    with pytest.raises(PlatformVersionTooOldError) as exc_info:
        release_import.import_release(
            db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
        )
    assert exc_info.value.code == "PLT-COMPATIBILITY-002"


# --- Immutability ---


def test_import_does_not_modify_release_package_contents(db_engine, tmp_path):
    import hashlib
    from pathlib import Path

    _stage(tmp_path, "valid-release-1.0.0")
    release_dir = tmp_path / "valid-release-1.0.0"

    before = {
        str(p.relative_to(release_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(release_dir.rglob("*"))
        if p.is_file()
    }

    candidate_id = _scan_and_get_candidate_id(db_engine, tmp_path, "valid-release-1.0.0")
    release_import.import_release(
        db_engine, _config(tmp_path), candidate_id=candidate_id, requested_by="operator:test"
    )

    after = {
        str(p.relative_to(release_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(release_dir.rglob("*"))
        if p.is_file()
    }

    assert before == after
