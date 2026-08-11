import shutil
from pathlib import Path

import pytest

from rah_platform import release_discovery
from rah_platform.errors import CandidateNotFoundError, ReleaseStorageUnavailableError

FIXTURES_ROOT = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "releases"


def _copy_fixtures(tmp_path, *names: str):
    for name in names:
        shutil.copytree(FIXTURES_ROOT / name, tmp_path / name)
    return str(tmp_path)


# --- Empty Storage ---


def test_empty_storage_returns_zero_candidates(db_engine, tmp_path):
    result = release_discovery.scan_releases(db_engine, str(tmp_path))
    assert result["candidate_count"] == 0
    assert result["candidates"] == []


# --- Valid Candidate ---


def test_valid_candidate_detected_correctly(db_engine, tmp_path):
    incoming = _copy_fixtures(tmp_path, "valid-release-1.0.0")
    result = release_discovery.scan_releases(db_engine, incoming)
    assert result["candidate_count"] == 1
    candidate = result["candidates"][0]
    assert candidate["directory_name"] == "valid-release-1.0.0"
    assert candidate["application_slug"] == "golden-test-app"
    assert candidate["release_version"] == "1.0.0"
    assert candidate["discovery_state"] == "READY_FOR_IMPORT"
    assert candidate["issues"] == []


# --- Multiple Candidates ---


def test_multiple_candidates_all_returned_predictably(db_engine, tmp_path):
    incoming = _copy_fixtures(
        tmp_path, "valid-release-1.0.0", "incomplete-release.partial", "missing-manifest", "malformed-manifest"
    )
    result = release_discovery.scan_releases(db_engine, incoming)
    assert result["candidate_count"] == 4
    directory_names = [c["directory_name"] for c in result["candidates"]]
    assert directory_names == sorted(directory_names)
    assert set(directory_names) == {
        "valid-release-1.0.0",
        "incomplete-release.partial",
        "missing-manifest",
        "malformed-manifest",
    }


# --- Incomplete Copy ---


def test_incomplete_copy_classified_incomplete(db_engine, tmp_path):
    incoming = _copy_fixtures(tmp_path, "incomplete-release.partial")
    result = release_discovery.scan_releases(db_engine, incoming)
    candidate = result["candidates"][0]
    assert candidate["discovery_state"] == "INCOMPLETE"
    # identity was still readable even though the transfer isn't finished
    assert candidate["application_slug"] == "golden-test-app"


# --- Missing Manifest ---


def test_missing_manifest_classified_invalid(db_engine, tmp_path):
    incoming = _copy_fixtures(tmp_path, "missing-manifest")
    result = release_discovery.scan_releases(db_engine, incoming)
    candidate = result["candidates"][0]
    assert candidate["discovery_state"] == "INVALID_MANIFEST"
    assert candidate["application_slug"] is None
    assert candidate["issues"]


def test_malformed_manifest_classified_invalid(db_engine, tmp_path):
    incoming = _copy_fixtures(tmp_path, "malformed-manifest")
    result = release_discovery.scan_releases(db_engine, incoming)
    candidate = result["candidates"][0]
    assert candidate["discovery_state"] == "INVALID_MANIFEST"
    assert candidate["application_slug"] is None


# --- Repeat Scan ---


def test_repeat_scan_does_not_duplicate_candidates(db_engine, tmp_path):
    incoming = _copy_fixtures(tmp_path, "valid-release-1.0.0")
    first = release_discovery.scan_releases(db_engine, incoming)
    second = release_discovery.scan_releases(db_engine, incoming)

    assert first["candidates"][0]["candidate_id"] == second["candidates"][0]["candidate_id"]

    listed = release_discovery.list_candidates(db_engine)
    assert len(listed["items"]) == 1


def test_repeat_scan_reflects_updated_state(db_engine, tmp_path):
    incoming = _copy_fixtures(tmp_path, "incomplete-release.partial")
    first = release_discovery.scan_releases(db_engine, incoming)
    assert first["candidates"][0]["discovery_state"] == "INCOMPLETE"

    # the transfer "finishes": checksums arrive
    import os

    os.makedirs(f"{incoming}/incomplete-release.partial/checksums", exist_ok=True)
    with open(f"{incoming}/incomplete-release.partial/checksums/SHA256SUMS", "w") as f:
        f.write("# now complete\n")

    second = release_discovery.scan_releases(db_engine, incoming)
    assert second["candidates"][0]["discovery_state"] == "READY_FOR_IMPORT"
    assert second["candidates"][0]["candidate_id"] == first["candidates"][0]["candidate_id"]


# --- Read-Only Behavior ---


def test_scan_does_not_touch_operations(db_engine, tmp_path):
    incoming = _copy_fixtures(tmp_path, "valid-release-1.0.0")
    release_discovery.scan_releases(db_engine, incoming)

    import sqlalchemy as sa

    with db_engine.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM operations")).scalar()
    assert count == 0


# --- Storage Unavailable ---


def test_scan_missing_incoming_directory_raises_structured_error(db_engine, tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(ReleaseStorageUnavailableError) as exc_info:
        release_discovery.scan_releases(db_engine, str(missing))
    assert exc_info.value.code == "PLT-STORAGE-001"


# --- get_candidate ---


def test_get_candidate_not_found(db_engine):
    with pytest.raises(CandidateNotFoundError) as exc_info:
        release_discovery.get_candidate(db_engine, "00000000-0000-0000-0000-000000000000")
    assert exc_info.value.code == "PLT-STORAGE-004"


def test_get_candidate_returns_scanned_candidate(db_engine, tmp_path):
    incoming = _copy_fixtures(tmp_path, "valid-release-1.0.0")
    scanned = release_discovery.scan_releases(db_engine, incoming)
    candidate_id = scanned["candidates"][0]["candidate_id"]

    fetched = release_discovery.get_candidate(db_engine, candidate_id)
    assert fetched["candidate_id"] == candidate_id
    assert fetched["directory_name"] == "valid-release-1.0.0"
