"""Real Docker builds against the real host Engine — `package_release()`
calls `construct_release()` (P6) internally, which calls
`build_release_images()` (P5). `app`'s Dockerfile is deliberately `FROM
scratch` (no network pull) to keep these fast, matching P6's own tests.
"""

import json
import subprocess
from pathlib import Path

import docker
import pytest
import yaml

from rah_packager.compliance_report import validate_compliance_report
from rah_packager.engineering_answers import compute_inspection_fingerprint
from rah_packager.errors import (
    PlanDirtySourceError,
    ReleaseAlreadyExistsError,
    ReleaseComplianceFailedError,
    ReleaseNotFoundError,
)
from rah_packager.finalize_release import package_release
from rah_packager.inspection import inspect_project
from rah_packager.project_state import build_initial_state, project_state_path
from rah_packager.release_manifest import validate_release_manifest
from rah_packager.validate_answers import default_answers_path
from rah_packager.validate_release import validate_release

SLUG = "test-package-app"
IMAGE_TAG = f"rah-{SLUG}-app:1.0.0"


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _valid_answers(inspection_result: dict) -> dict:
    return {
        "schema_version": "1.0",
        "based_on": {
            "git_commit": inspection_result["git"]["commit"],
            "inspection_fingerprint": compute_inspection_fingerprint(inspection_result),
        },
        "application": {"description": "A package-command test application."},
        "compatibility": {"minimum_rah_oip_version": "1.0", "supported_architectures": ["amd64"]},
        "deployment": {
            "entrypoints": {
                "install": "scripts/install_offline.sh",
                "verify": "scripts/verify_installation.sh",
            },
            "supported_operations": {"fresh_install": True, "downgrade": False},
        },
        "configuration": {"inputs": []},
        "database": {"required": False},
        "persistent_state": {"preserve_during_update": []},
        "offline_requirements": {
            "public_internet_required": False,
            "public_registry_required": False,
            "public_cdn_required": False,
            "online_model_registry_required": False,
        },
        "models": {"required": False},
        "client": {"preparation_required": False, "https_required": False},
        "verification": {"entrypoint": "scripts/verify_installation.sh", "required_checks": ["health"]},
        "documentation": {
            "release_notes": "RELEASE_NOTES.md",
            "installation": "RELEASE_NOTES.md",
            "update": "RELEASE_NOTES.md",
            "recovery": "RELEASE_NOTES.md",
            "known_issues": "RELEASE_NOTES.md",
        },
    }


def _setup_repo(tmp_path, name="Test Package App"):
    (tmp_path / "scripts").mkdir()
    install = tmp_path / "scripts" / "install_offline.sh"
    install.write_text("#!/bin/sh\necho install\n")
    install.chmod(0o755)
    verify = tmp_path / "scripts" / "verify_installation.sh"
    verify.write_text("#!/bin/sh\necho verify\n")
    verify.chmod(0o755)
    (tmp_path / "RELEASE_NOTES.md").write_text("# Release Notes")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "Dockerfile").write_text("FROM scratch\nCOPY hello.txt /hello.txt\n")
    (tmp_path / "app" / "hello.txt").write_text("hello\n")
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  app:\n    build:\n      context: ./app\n      dockerfile: Dockerfile\n"
    )

    _git(tmp_path, "init", "--quiet", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "init")

    state = build_initial_state(name, SLUG, "1.0.0")
    state_path = project_state_path(tmp_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state))

    inspection_result = inspect_project(tmp_path)
    answers_path = default_answers_path(tmp_path)
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text(json.dumps(_valid_answers(inspection_result)))


def _remove_image():
    try:
        docker.from_env().images.remove(IMAGE_TAG, force=True)
    except docker.errors.ImageNotFound:
        pass


# --- Valid Release -> PASS, full closure, project state updated only after success ---


def test_package_release_produces_a_finalized_pass_release(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    output_dir = tmp_path / "output"

    try:
        result = package_release(project, output_dir)

        assert result["overall_result"] == "PASS"
        release_dir = Path(result["release_directory"])

        manifest = yaml.safe_load((release_dir / "release.yaml").read_text())
        validate_release_manifest(manifest)

        report = json.loads((release_dir / "compliance" / "release-compliance-report.json").read_text())
        validate_compliance_report(report)
        assert report["overall_result"] == "PASS"
        assert report["summary"]["rules_failed"] == 0
        assert report["summary"]["rules_executed"] >= 40  # RC-CON + full stage-A, not RC-INT/RC-REPRO

        checksum_path = release_dir / "checksums" / "SHA256SUMS"
        assert checksum_path.is_file()
        # the compliance report itself must be covered by the final checksums
        assert "compliance/release-compliance-report.json" in checksum_path.read_text()

        assert result["release_fingerprint"].startswith("sha256:")

        # Project Version State updated only now, after everything passed.
        state = json.loads(project_state_path(project).read_text())
        assert state["versioning"]["current_release"] == "1.0.0"
        assert len(state["release_history"]) == 1
        assert state["release_history"][0]["version"] == "1.0.0"
        assert state["release_history"][0]["source"]["git_commit"] == manifest["source"]["git_commit"]
    finally:
        _remove_image()


# --- Independent re-validation of the finalized Release: also PASS ---


def test_validate_release_passes_on_the_finalized_release(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    output_dir = tmp_path / "output"

    try:
        result = package_release(project, output_dir)
        release_dir = Path(result["release_directory"])

        validation = validate_release(release_dir)

        assert validation["overall_result"] == "PASS"
        assert validation["checksum_mismatches"] == []
        assert not any(r["result"] == "FAIL" for r in validation["rules"])
        # RC-INT rules only make sense once checksums/compliance exist —
        # confirm they actually ran (not NOT_EXECUTED) and passed.
        int_rules = [r for r in validation["rules"] if r["category"] == "RC-INT"]
        assert len(int_rules) == 4
        assert all(r["result"] == "PASS" for r in int_rules)
    finally:
        _remove_image()


def test_validate_release_reports_identity_not_applicable_without_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    output_dir = tmp_path / "output"

    try:
        result = package_release(project, output_dir)
        validation = validate_release(Path(result["release_directory"]))  # no --project

        man_002 = next(r for r in validation["rules"] if r["id"] == "RC-MAN-002")
        assert man_002["result"] == "NOT_APPLICABLE"

        validation_with_project = validate_release(Path(result["release_directory"]), project)
        man_002_with_project = next(r for r in validation_with_project["rules"] if r["id"] == "RC-MAN-002")
        assert man_002_with_project["result"] == "PASS"
    finally:
        _remove_image()


# --- Checksum Mismatch -> FAIL ---


def test_validate_release_detects_tampering_after_finalization(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    output_dir = tmp_path / "output"

    try:
        result = package_release(project, output_dir)
        release_dir = Path(result["release_directory"])

        (release_dir / "scripts" / "install_offline.sh").write_text("#!/bin/sh\necho TAMPERED\n")

        validation = validate_release(release_dir)

        assert validation["overall_result"] == "FAIL"
        assert any("install_offline.sh" in m for m in validation["checksum_mismatches"])
    finally:
        _remove_image()


# --- Missing Artifact -> FAIL ---


def test_package_release_fails_when_a_declared_artifact_is_deleted_before_finalization(tmp_path, monkeypatch):
    """Simulates a filesystem-level artifact loss between construction and
    the compliance check by deleting a declared documentation file right
    after `construct_release` would have placed it — exercised here via
    the same real pipeline, then asserting `rah validate` (not `package`,
    since `package`'s own construct step wouldn't naturally produce this
    state) correctly reports the gap as a real Artifact Contract failure.
    """
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    output_dir = tmp_path / "output"

    try:
        result = package_release(project, output_dir)
        release_dir = Path(result["release_directory"])
        (release_dir / "documentation" / "RELEASE_NOTES.md").unlink()

        validation = validate_release(release_dir)

        assert validation["overall_result"] == "FAIL"
        art_002 = next(r for r in validation["rules"] if r["id"] == "RC-ART-002")
        assert art_002["result"] == "FAIL"
    finally:
        _remove_image()


# --- Duplicate Release -> FAIL (reuses rah plan's existing gate) ---


def test_package_release_rejects_duplicate_version(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    output_dir = tmp_path / "output"

    try:
        package_release(project, output_dir)  # first release: 1.0.0, current_release now 1.0.0

        # A patch bump from 1.0.0 proposes 1.0.1 — seed that version into
        # history directly (as if a prior run had already produced it) so
        # the next real patch-bump attempt collides with it for real.
        state_path = project_state_path(project)
        state = json.loads(state_path.read_text())
        state["release_history"].append(
            {
                "version": "1.0.1",
                "created_at": "2026-01-01T00:00:00Z",
                "source": {"git_commit": "0" * 40, "git_tag": None},
                "summary": "manually seeded duplicate target",
            }
        )
        state_path.write_text(json.dumps(state))

        with pytest.raises(Exception):
            package_release(project, output_dir, increment="patch")  # would propose 1.0.1 again
    finally:
        _remove_image()


# --- Existing Final Release -> never silently overwritten ---


def test_package_release_never_overwrites_an_existing_finalized_release(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    output_dir = tmp_path / "output"
    release_dir = output_dir / "Test Package App_Release_1.0.0"

    # Simulate an already-finalized Release at the target path without a
    # real build — package_release must refuse before touching it.
    (release_dir / "compliance").mkdir(parents=True)
    (release_dir / "compliance" / "release-compliance-report.json").write_text("{}")
    (release_dir / "scripts").mkdir()
    (release_dir / "scripts" / "sentinel.txt").write_text("do not touch")

    with pytest.raises(ReleaseAlreadyExistsError) as exc_info:
        package_release(project, output_dir)
    assert exc_info.value.code == "PKG-RELEASE-ALREADY-EXISTS"
    assert (release_dir / "scripts" / "sentinel.txt").is_file()  # untouched


# --- Finalization Atomicity: a compliance failure never touches release history ---


def test_compliance_failure_does_not_modify_release_history(tmp_path):
    """RC-SCR-002 ('script located inside scripts/') is structurally
    unreachable as a FAIL here: P2 can't discover a script outside a
    scripts/-named directory in the first place, so P3's own consistency
    check already rejects it long before RC-SCR-002 would run. RC-CFG-001
    (real-looking secret in a configuration template) is a genuine gap
    P3 doesn't check at all — P3 never inspects template *content* — so
    it's a real, reachable P7-only failure to exercise atomicity with.
    """
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    (project / ".env.template").write_text("DATABASE_PASSWORD=SuperSecretRealValue123\n")
    _git(project, "add", ".env.template")
    _git(project, "commit", "--quiet", "-m", "add configuration template with a real secret")

    answers_path = default_answers_path(project)
    answers = json.loads(answers_path.read_text())
    answers["configuration"] = {
        "template": ".env.template",
        "inputs": [
            {
                "key": "DATABASE_PASSWORD",
                "label": "Database password",
                "type": "password",
                "required": True,
                "source": "operator",
            }
        ],
    }
    inspection_result = inspect_project(project)
    answers["based_on"] = {
        "git_commit": inspection_result["git"]["commit"],
        "inspection_fingerprint": compute_inspection_fingerprint(inspection_result),
    }
    answers_path.write_text(json.dumps(answers))

    output_dir = tmp_path / "output"
    before_state = json.loads(project_state_path(project).read_text())

    try:
        with pytest.raises(ReleaseComplianceFailedError) as exc_info:
            package_release(project, output_dir)
        assert any(r["id"] == "RC-CFG-001" for r in exc_info.value.failed_rules)

        after_state = json.loads(project_state_path(project).read_text())
        assert after_state == before_state  # release history untouched
    finally:
        _remove_image()


# --- rah validate against a path with no release.yaml ---


def test_validate_release_reports_missing_release(tmp_path):
    with pytest.raises(ReleaseNotFoundError) as exc_info:
        validate_release(tmp_path / "nowhere")
    assert exc_info.value.code == "PKG-RELEASE-NOT-FOUND"
