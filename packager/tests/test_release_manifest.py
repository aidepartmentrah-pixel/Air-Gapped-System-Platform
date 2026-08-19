import json
from pathlib import Path

import pytest

from rah_packager.errors import (
    ReleaseManifestIncompleteError,
    ReleaseManifestSchemaError,
)
from rah_packager.release_manifest import (
    RELEASE_MANIFEST_SCHEMA,
    build_release_manifest,
    check_answers_sufficient_for_manifest,
    validate_release_manifest,
)

REAL_CONTRACT_SCHEMA_PATH = (
    Path(__file__).parent.parent.parent / "contracts" / "1.0" / "release-manifest.schema.json"
)


# --- Embedded schema never drifts from the real, frozen Contract file ---


def _strip_metadata(node):
    """$schema/$id/title/description are documentation, not structural —
    the embedded copy deliberately drops them everywhere, not just at the
    top level (see release_manifest.py's module docstring). Structural
    equivalence is what this test guards, not byte-identical prose.
    """
    if isinstance(node, dict):
        return {
            key: _strip_metadata(value)
            for key, value in node.items()
            if key not in ("$schema", "$id", "title", "description")
        }
    if isinstance(node, list):
        return [_strip_metadata(item) for item in node]
    return node


def test_embedded_schema_matches_real_contract_file():
    real_schema = json.loads(REAL_CONTRACT_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert _strip_metadata(RELEASE_MANIFEST_SCHEMA) == _strip_metadata(real_schema)


def _valid_answers(**overrides) -> dict:
    answers = {
        "application": {"description": "A test application."},
        "compatibility": {"minimum_rah_oip_version": "1.0", "supported_architectures": ["amd64"]},
        "deployment": {
            "entrypoints": {"install": "scripts/install_offline.sh"},
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
        "verification": {"entrypoint": "verification/verify.sh", "required_checks": []},
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


def _docker_images():
    return [
        {
            "service": "app",
            "repository": "rah-test-app-app",
            "tag": "1.0.0",
            "archive": "docker-images/rah-test-app-app_1.0.0.tar",
            "required": True,
        }
    ]


# --- check_answers_sufficient_for_manifest ---


def test_missing_verification_entrypoint_blocks_manifest():
    answers = _valid_answers()
    answers["verification"] = {"entrypoint": None, "required_checks": []}

    with pytest.raises(ReleaseManifestIncompleteError) as exc_info:
        check_answers_sufficient_for_manifest(answers)
    assert exc_info.value.code == "PKG-MANIFEST-INCOMPLETE"


def test_configuration_inputs_without_template_blocks_manifest():
    answers = _valid_answers()
    answers["configuration"] = {
        "inputs": [
            {
                "key": "APP_PORT",
                "label": "Port",
                "type": "port",
                "required": True,
                "source": "operator",
            }
        ]
    }

    with pytest.raises(ReleaseManifestIncompleteError):
        check_answers_sufficient_for_manifest(answers)


def test_configuration_inputs_with_template_is_sufficient():
    answers = _valid_answers()
    answers["configuration"] = {
        "template": "configuration/production.env.template",
        "inputs": [
            {
                "key": "APP_PORT",
                "label": "Port",
                "type": "port",
                "required": True,
                "source": "operator",
            }
        ],
    }

    check_answers_sufficient_for_manifest(answers)  # must not raise


# --- build_release_manifest ---


def test_build_release_manifest_produces_schema_valid_output():
    manifest = build_release_manifest(
        application={"name": "Test App", "slug": "test-app"},
        version="1.0.0",
        summary="Test App 1.0.0",
        project_path="/repo",
        git_facts={
            "commit": "a" * 40,
            "tag": None,
            "state": "clean",
            "remote_url": None,
        },
        answers=_valid_answers(),
        docker_images=_docker_images(),
        model_artifacts=[],
    )

    validate_release_manifest(manifest)  # must not raise
    assert manifest["application"] == {
        "name": "Test App",
        "slug": "test-app",
        "description": "A test application.",
    }
    assert manifest["release"]["version"] == "1.0.0"
    assert manifest["release"]["engineering_state"] == "awaiting_offline_qualification"
    assert manifest["source"]["repository"] == "/repo"  # no remote configured, falls back
    assert manifest["source"]["source_dirty"] is False
    assert "git_tag" not in manifest["source"]  # omitted, not null, when no tag exists
    assert manifest["deployment"]["canonical_path"] == "/opt/rah/apps/test-app"
    assert manifest["deployment"]["compose_project_name"] == "test-app"  # defaulted from slug
    assert manifest["docker"]["images"] == _docker_images()
    assert manifest["models"] == {"required": False, "artifacts": []}
    assert manifest["integrity"] == {
        "checksum_algorithm": "sha256",
        "checksum_file": "checksums/SHA256SUMS",
    }


def test_build_release_manifest_carries_through_resolved_model_artifacts():
    resolved_artifact = {
        "id": "m1",
        "version": "1.0.0",
        "checksum": "sha256:" + "a" * 64,
        "baked_into_image": "app",
    }
    answers = _valid_answers()
    answers["models"] = {"required": True}

    manifest = build_release_manifest(
        application={"name": "Test App", "slug": "test-app"},
        version="1.0.0",
        summary="s",
        project_path="/repo",
        git_facts={"commit": "a" * 40, "tag": None, "state": "clean", "remote_url": None},
        answers=answers,
        docker_images=_docker_images(),
        model_artifacts=[resolved_artifact],
    )

    validate_release_manifest(manifest)  # must not raise — real, frozen schema
    assert manifest["models"] == {"required": True, "artifacts": [resolved_artifact]}


def test_build_release_manifest_uses_remote_url_and_tag_when_present():
    manifest = build_release_manifest(
        application={"name": "Test App", "slug": "test-app"},
        version="1.0.0",
        summary="s",
        project_path="/repo",
        git_facts={
            "commit": "a" * 40,
            "tag": "v1.0.0",
            "state": "clean",
            "remote_url": "https://example.com/test-app.git",
        },
        answers=_valid_answers(),
        docker_images=_docker_images(),
        model_artifacts=[],
    )

    assert manifest["source"]["repository"] == "https://example.com/test-app.git"
    assert manifest["source"]["git_tag"] == "v1.0.0"


def test_build_release_manifest_rejects_insufficient_answers():
    answers = _valid_answers()
    answers["verification"] = {"entrypoint": None, "required_checks": []}

    with pytest.raises(ReleaseManifestIncompleteError):
        build_release_manifest(
            application={"name": "Test App", "slug": "test-app"},
            version="1.0.0",
            summary="s",
            project_path="/repo",
            git_facts={"commit": "a" * 40, "tag": None, "state": "clean", "remote_url": None},
            answers=answers,
            docker_images=_docker_images(),
            model_artifacts=[],
        )


def test_no_images_fails_manifest_schema_minitems():
    manifest = build_release_manifest(
        application={"name": "Test App", "slug": "test-app"},
        version="1.0.0",
        summary="s",
        project_path="/repo",
        git_facts={"commit": "a" * 40, "tag": None, "state": "clean", "remote_url": None},
        answers=_valid_answers(),
        docker_images=[],
        model_artifacts=[],
    )

    with pytest.raises(ReleaseManifestSchemaError) as exc_info:
        validate_release_manifest(manifest)
    assert exc_info.value.code == "PKG-MANIFEST-SCHEMA-INVALID"
