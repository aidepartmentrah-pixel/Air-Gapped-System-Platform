"""Real Docker builds against the real host Engine — `construct_release()`
calls `build_release_images()` internally, so every test here that
reaches the build step is a real proof, not a mock. `app`'s Dockerfile
is deliberately `FROM scratch` (no network pull) to keep these fast.
"""

import json
import subprocess
from pathlib import Path

import docker
import pytest
import yaml

from rah_packager.construct_release import construct_release
from rah_packager.engineering_answers import compute_inspection_fingerprint
from rah_packager.errors import (
    PlanDirtySourceError,
    ReleaseManifestIncompleteError,
)
from rah_packager.inspection import inspect_project
from rah_packager.project_state import build_initial_state, project_state_path
from rah_packager.release_manifest import validate_release_manifest
from rah_packager.validate_answers import default_answers_path

SLUG = "test-construct-app"
IMAGE_TAG = f"rah-{SLUG}-app:1.0.0"


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _valid_answers(inspection_result: dict, **overrides) -> dict:
    answers = {
        "schema_version": "1.0",
        "based_on": {
            "git_commit": inspection_result["git"]["commit"],
            "inspection_fingerprint": compute_inspection_fingerprint(inspection_result),
        },
        "application": {"description": "A construction test application."},
        "compatibility": {"minimum_rah_oip_version": "1.0", "supported_architectures": ["amd64"]},
        "deployment": {
            "entrypoints": {
                "install": "scripts/install_offline.sh",
                "verify": "scripts/verify_installation.sh",
            },
            "supported_operations": {"fresh_install": True},
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
        "verification": {"entrypoint": "scripts/verify_installation.sh", "required_checks": []},
        "documentation": {
            "release_notes": "RELEASE_NOTES.md",
            "installation": "RELEASE_NOTES.md",
            "update": "RELEASE_NOTES.md",
            "recovery": "RELEASE_NOTES.md",
            "known_issues": "RELEASE_NOTES.md",
        },
    }
    answers.update(overrides)
    return answers


def _setup_repo(tmp_path, name="Test Construct App"):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "install_offline.sh").write_text("#!/bin/sh\necho install\n")
    (tmp_path / "scripts" / "verify_installation.sh").write_text("#!/bin/sh\necho verify\n")
    (tmp_path / "RELEASE_NOTES.md").write_text("# Release Notes")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "Dockerfile").write_text("FROM scratch\nCOPY hello.txt /hello.txt\n")
    (tmp_path / "app" / "hello.txt").write_text("hello\n")
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  app:\n    build:\n      context: ./app\n      dockerfile: Dockerfile\n"
        "    environment:\n      APP_MODE: production\n"
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

    return inspection_result


def _remove_image():
    try:
        docker.from_env().images.remove(IMAGE_TAG, force=True)
    except docker.errors.ImageNotFound:
        pass


# --- Happy path: a complete, schema-valid candidate Release ---


def test_construct_release_produces_valid_candidate(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    output_dir = tmp_path / "output"

    try:
        result = construct_release(project, output_dir)

        release_dir = output_dir / f"{result['application']['name']}_Release_1.0.0"
        assert result["release_directory"] == str(release_dir)
        assert release_dir.is_dir()

        # --- Manifest Schema Contract ---
        manifest = yaml.safe_load((release_dir / "release.yaml").read_text(encoding="utf-8"))
        validate_release_manifest(manifest)  # must not raise
        assert manifest["release"]["version"] == "1.0.0"
        assert manifest["application"]["slug"] == SLUG

        # --- Directory Contract ---
        assert (release_dir / "compose" / "docker-compose.yml").is_file()
        assert (release_dir / "docker-images").is_dir()
        assert (release_dir / "scripts" / "install_offline.sh").is_file()
        assert (release_dir / "scripts" / "verify_installation.sh").is_file()
        assert (release_dir / "verification" / "verify_installation.sh").is_file()
        assert (release_dir / "documentation" / "RELEASE_NOTES.md").is_file()

        # --- Artifact Contract: declared artifacts actually exist ---
        for image in manifest["docker"]["images"]:
            assert (release_dir / image["archive"]).is_file()

        # --- Script Contract: declared lifecycle scripts actually exist ---
        for script_path in manifest["deployment"]["entrypoints"].values():
            assert (release_dir / script_path).is_file()

        # --- Identity Consistency: slug/version match across every source ---
        assert manifest["application"]["slug"] == SLUG
        assert release_dir.name.endswith("_Release_1.0.0")
        assert manifest["release"]["version"] == "1.0.0"

        # Compose file rewritten: build -> image, everything else preserved.
        compose = yaml.safe_load((release_dir / "compose" / "docker-compose.yml").read_text())
        assert "build" not in compose["services"]["app"]
        assert compose["services"]["app"]["image"] == IMAGE_TAG
        assert compose["services"]["app"]["environment"]["APP_MODE"] == "production"
    finally:
        _remove_image()


# --- Reuses rah plan's gates directly (no re-implementation) ---


def test_construct_release_rejects_dirty_repo(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    (project / "scripts" / "install_offline.sh").write_text("#!/bin/sh\necho changed\n")

    with pytest.raises(PlanDirtySourceError):
        construct_release(project, tmp_path / "output")


# --- Fails fast, before any Docker build, on an insufficient answer set ---


def test_construct_release_blocks_on_missing_verification_entrypoint(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    inspection_result = _setup_repo(project)
    answers_path = default_answers_path(project)
    answers = _valid_answers(inspection_result)
    answers["verification"] = {"entrypoint": None, "required_checks": []}
    answers_path.write_text(json.dumps(answers))

    with pytest.raises(ReleaseManifestIncompleteError):
        construct_release(project, tmp_path / "output")

    # No image was ever built — this failed before the expensive step.
    with pytest.raises(docker.errors.ImageNotFound):
        docker.from_env().images.get(IMAGE_TAG)


# --- Unconditional overwrite: re-running never refuses ---


def test_construct_release_overwrites_unconditionally(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)
    output_dir = tmp_path / "output"

    try:
        first = construct_release(project, output_dir)
        release_dir = Path(first["release_directory"])
        # Poison the directory with a stray file from a hypothetical prior
        # attempt — a real re-run must not leave this behind.
        (release_dir / "stray.txt").write_text("leftover")

        second = construct_release(project, output_dir)
        assert second["release_directory"] == first["release_directory"]
        assert (release_dir / "release.yaml").is_file()
        assert not (release_dir / "stray.txt").exists()
    finally:
        _remove_image()


# --- RC-REPRO-001: two independent candidate Releases are structurally equal ---


def test_construct_release_is_reproducible(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _setup_repo(project)

    try:
        first = construct_release(project, tmp_path / "output-a")
        second = construct_release(project, tmp_path / "output-b")

        manifest_a = yaml.safe_load(
            (tmp_path / first["release_directory"] / "release.yaml").read_text()
        )
        manifest_b = yaml.safe_load(
            (tmp_path / second["release_directory"] / "release.yaml").read_text()
        )
        # created_at is inherently unique per build (real timestamp) — the
        # one documented, deliberate exclusion (see P6's RC-REPRO-001).
        del manifest_a["release"]["created_at"]
        del manifest_b["release"]["created_at"]
        assert manifest_a == manifest_b

        def _relative_files(base):
            return sorted(
                str(p.relative_to(base)).replace("\\", "/")
                for p in base.rglob("*")
                if p.is_file()
            )

        dir_a = tmp_path / first["release_directory"]
        dir_b = tmp_path / second["release_directory"]
        assert _relative_files(dir_a) == _relative_files(dir_b)

        # Non-image file contents are byte-identical too (release.yaml
        # already compared above, minus its inherently-unique created_at).
        # Docker image archive byte-equality is the one documented,
        # deliberate exclusion (depends on `docker build`'s own
        # reproducibility).
        for relative in _relative_files(dir_a):
            if relative.startswith("docker-images/") or relative == "release.yaml":
                continue
            assert (dir_a / relative).read_bytes() == (dir_b / relative).read_bytes(), relative
    finally:
        _remove_image()
