"""The Release Manifest (`release.yaml`) — P6 Release Construction.

`RELEASE_MANIFEST_SCHEMA` is transcribed verbatim from the real, frozen
`contracts/1.0/release-manifest.schema.json` — not `$ref`'d or loaded
from that file at runtime, the same "embed, don't read the Contract file
at runtime" choice P3 made for `ENGINEERING_ANSWERS_SCHEMA`. Consistency
with the real file is a test concern
(`test_release_manifest.py::test_embedded_schema_matches_real_contract_file`),
not a runtime dependency — the Packager never needs the `contracts/`
directory mounted into its container.

`build_release_manifest()` maps every one of the manifest's 16 required
sections to exactly one source, per the architecture's own P6 input list
(Project Version State + Inspection Result + Validated Engineering
Answers + Build Artifact Metadata + Release Plan):

- `manifest_schema_version`, `release.release_type`,
  `release.engineering_state`, `compatibility.release_contract_version`,
  `integrity.*` — constants.
- `application.name/slug`, `release.version` — Project Version State /
  Release Plan (already identity-consistent by construction, since both
  come from the same `packager_state`/`plan` objects, not re-typed).
- `source.*` — Inspection Result's `git` category (now including
  `remote_url`, added for this).
- Everything else — validated Engineering Answers, passed through
  structurally unchanged where the two schemas already match field-for-
  field (P3's own docstring: compatibility/configuration/database/
  persistent_state/offline_requirements/client/documentation), with the
  few genuine manifest/answers schema gaps resolved explicitly rather
  than silently defaulted — see `_check_answers_sufficient()`.
- `docker.images` — Build Artifact Metadata (P5's `build_release_images()`
  result), built-services only; a service with only a prebuilt `image:`
  reference has no exported archive in this Packager version and is
  deliberately not represented here (see `docker_build.py`'s own scope
  note — same open gap, not resolved in this slice either).
"""

from __future__ import annotations

import jsonschema

from rah_packager.errors import (
    ReleaseManifestIncompleteError,
    ReleaseManifestSchemaError,
)

MANIFEST_SCHEMA_VERSION = "1.0"
RELEASE_CONTRACT_VERSION = "1.0"

# Verbatim transcription of contracts/1.0/release-manifest.schema.json.
RELEASE_MANIFEST_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://rah-release-system/contracts/1.0/release-manifest.schema.json",
    "title": "RAH Application Release Manifest",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "manifest_schema_version",
        "application",
        "release",
        "source",
        "compatibility",
        "deployment",
        "configuration",
        "docker",
        "database",
        "persistent_state",
        "offline_requirements",
        "models",
        "client",
        "verification",
        "documentation",
        "integrity",
    ],
    "properties": {
        "manifest_schema_version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+$"},
        "application": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "slug", "description"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "slug": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$"},
                "description": {"type": "string"},
            },
        },
        "release": {
            "type": "object",
            "additionalProperties": False,
            "required": ["version", "created_at", "summary", "release_type", "engineering_state"],
            "properties": {
                "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
                "created_at": {"type": "string", "format": "date-time"},
                "summary": {"type": "string"},
                "release_type": {"type": "string", "const": "application"},
                "engineering_state": {
                    "type": "string",
                    "enum": ["awaiting_offline_qualification"],
                },
            },
        },
        "source": {
            "type": "object",
            "additionalProperties": False,
            "required": ["repository", "git_commit", "source_dirty"],
            "properties": {
                "repository": {"type": "string"},
                "git_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                "git_tag": {"type": "string"},
                "source_dirty": {"type": "boolean"},
            },
        },
        "compatibility": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "release_contract_version",
                "minimum_rah_oip_version",
                "supported_architectures",
            ],
            "properties": {
                "release_contract_version": {"type": "string", "const": "1.0"},
                "minimum_rah_oip_version": {"type": "string"},
                "supported_architectures": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["amd64", "arm64"]},
                    "minItems": 1,
                },
                "required_shared_services": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "minimum_version", "required"],
                        "properties": {
                            "id": {"type": "string"},
                            "minimum_version": {"type": "string"},
                            "required": {"type": "boolean"},
                        },
                    },
                },
            },
        },
        "deployment": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "canonical_path",
                "compose_project_name",
                "entrypoints",
                "supported_operations",
                "transition",
            ],
            "properties": {
                "canonical_path": {"type": "string"},
                "compose_project_name": {"type": "string"},
                "entrypoints": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "install": {"type": "string"},
                        "update": {"type": "string"},
                        "verify": {"type": "string"},
                        "backup": {"type": "string"},
                        "restore": {"type": "string"},
                    },
                },
                "supported_operations": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["fresh_install"],
                    "properties": {
                        "fresh_install": {"type": "boolean"},
                        "update": {"type": "boolean", "default": False},
                        "downgrade": {"type": "boolean", "default": False},
                        "reinstall": {"type": "boolean"},
                    },
                },
                "transition": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "accepted_installed_versions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "requires_existing_deployment_for_update": {"type": "boolean"},
                    },
                },
            },
        },
        "configuration": {
            "type": "object",
            "additionalProperties": False,
            "required": ["template", "inputs"],
            "properties": {
                "template": {"type": "string"},
                "inputs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["key", "label", "type", "required", "source"],
                        "properties": {
                            "key": {"type": "string"},
                            "label": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": [
                                    "string",
                                    "integer",
                                    "boolean",
                                    "port",
                                    "password",
                                    "path",
                                    "hostname",
                                    "ip_address",
                                    "url",
                                    "choice",
                                ],
                            },
                            "required": {"type": "boolean"},
                            "source": {
                                "type": "string",
                                "enum": ["operator", "generated", "platform", "fixed"],
                            },
                            "default": {},
                            "secret": {"type": "boolean"},
                        },
                    },
                },
            },
        },
        "docker": {
            "type": "object",
            "additionalProperties": False,
            "required": ["compose_file", "images"],
            "properties": {
                "compose_file": {"type": "string"},
                "images": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["service", "repository", "tag", "archive", "required"],
                        "properties": {
                            "service": {"type": "string"},
                            "repository": {"type": "string"},
                            "tag": {"type": "string"},
                            "archive": {"type": "string"},
                            "required": {"type": "boolean"},
                            "digest": {"type": "string"},
                        },
                    },
                },
            },
        },
        "database": {
            "type": "object",
            "additionalProperties": False,
            "required": ["required"],
            "properties": {
                "required": {"type": "boolean"},
                "platform": {
                    "type": "string",
                    "enum": ["postgresql", "sqlserver", "mysql", "sqlite"],
                },
                "deployment_mode": {
                    "type": "string",
                    "enum": ["application_managed", "shared_service", "external_existing"],
                },
                "target_schema_version": {"type": "string"},
                "initialization": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"entrypoint": {"type": "string"}},
                },
                "migration": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "required_for_update": {"type": "boolean"},
                        "entrypoint": {"type": "string"},
                    },
                },
                "backup_before_update": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "required": {"type": "boolean"},
                        "entrypoint": {"type": "string"},
                    },
                },
                "recovery": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"entrypoint": {"type": "string"}},
                },
            },
        },
        "persistent_state": {
            "type": "object",
            "additionalProperties": False,
            "required": ["preserve_during_update"],
            "properties": {
                "preserve_during_update": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "production_configuration",
                            "generated_credentials",
                            "database_data",
                            "docker_volumes",
                            "uploaded_files",
                            "certificates",
                            "deployment_history",
                        ],
                    },
                },
                "custom_paths": {"type": "array", "items": {"type": "string"}},
            },
        },
        "offline_requirements": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "public_internet_required",
                "public_registry_required",
                "public_cdn_required",
                "online_model_registry_required",
            ],
            "properties": {
                "public_internet_required": {"type": "boolean", "default": False},
                "public_registry_required": {"type": "boolean", "default": False},
                "public_cdn_required": {"type": "boolean", "default": False},
                "online_model_registry_required": {"type": "boolean", "default": False},
            },
        },
        "models": {
            "type": "object",
            "additionalProperties": False,
            "required": ["required", "artifacts"],
            "properties": {
                "required": {"type": "boolean"},
                "artifacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "version", "baked_into_image", "checksum"],
                        "properties": {
                            "id": {"type": "string"},
                            "version": {"type": "string"},
                            "source_registry": {"type": "string"},
                            "baked_into_image": {"type": "string"},
                            "checksum": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                        },
                    },
                },
            },
        },
        "client": {
            "type": "object",
            "additionalProperties": False,
            "required": ["preparation_required", "https_required"],
            "properties": {
                "preparation_required": {"type": "boolean"},
                "https_required": {"type": "boolean"},
                "secure_browser_capabilities": {"type": "array", "items": {"type": "string"}},
            },
        },
        "verification": {
            "type": "object",
            "additionalProperties": False,
            "required": ["entrypoint", "required_checks"],
            "properties": {
                "entrypoint": {"type": "string"},
                "required_checks": {"type": "array", "items": {"type": "string"}},
            },
        },
        "documentation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["release_notes", "installation", "update", "recovery", "known_issues"],
            "properties": {
                "release_notes": {"type": "string"},
                "installation": {"type": "string"},
                "update": {"type": "string"},
                "recovery": {"type": "string"},
                "known_issues": {"type": "string"},
            },
        },
        "integrity": {
            "type": "object",
            "additionalProperties": False,
            "required": ["checksum_algorithm", "checksum_file"],
            "properties": {
                "checksum_algorithm": {"type": "string", "const": "sha256"},
                "checksum_file": {"type": "string", "const": "checksums/SHA256SUMS"},
            },
        },
    },
}


def validate_release_manifest(manifest: dict) -> None:
    try:
        jsonschema.validate(manifest, RELEASE_MANIFEST_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ReleaseManifestSchemaError(exc.message) from exc


def check_answers_sufficient_for_manifest(answers: dict) -> None:
    """Real gaps between what P3 requires (structurally valid) and what
    P6 needs (a complete manifest) — see this module's docstring. Raised
    before attempting to build anything, so a failure here always names
    the actual missing input, never a downstream schema symptom.
    """
    if not answers["verification"].get("entrypoint"):
        raise ReleaseManifestIncompleteError(
            "verification.entrypoint is required to construct a Release but was not "
            "answered — engineering answers must supply a real verification entrypoint."
        )

    configuration = answers["configuration"]
    if configuration["inputs"] and not configuration.get("template"):
        raise ReleaseManifestIncompleteError(
            "configuration.inputs declares operator-facing inputs but "
            "configuration.template is missing — nothing to render them into."
        )


def build_release_manifest(
    *,
    application: dict,
    version: str,
    summary: str,
    project_path: str,
    git_facts: dict,
    answers: dict,
    docker_images: list[dict],
    model_artifacts: list[dict],
) -> dict:
    """Pure function: no filesystem access, no side effects. Every value
    either comes from an already-validated source (Project Version State,
    validated Engineering Answers, P5's build result) or is a documented
    constant/deterministic derivation — see this module's docstring for
    the full field-by-field mapping.
    """
    check_answers_sufficient_for_manifest(answers)

    manifest: dict = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "application": {
            "name": application["name"],
            "slug": application["slug"],
            "description": answers["application"]["description"],
        },
        "release": {
            "version": version,
            "created_at": _now_iso8601(),
            "summary": summary,
            "release_type": "application",
            "engineering_state": "awaiting_offline_qualification",
        },
        "source": {
            # No remote configured is a normal, valid state for a
            # local-only repository — falls back to the local path rather
            # than leaving this required field unfillable.
            "repository": git_facts.get("remote_url") or project_path,
            "git_commit": git_facts["commit"],
            "source_dirty": git_facts["state"] != "clean",
        },
        "compatibility": {
            "release_contract_version": RELEASE_CONTRACT_VERSION,
            **answers["compatibility"],
        },
        "deployment": {
            "canonical_path": f"/opt/rah/apps/{application['slug']}",
            "compose_project_name": (
                answers["deployment"].get("compose_project_name") or application["slug"]
            ),
            "entrypoints": dict(answers["deployment"].get("entrypoints") or {}),
            "supported_operations": dict(answers["deployment"]["supported_operations"]),
            "transition": dict(answers["deployment"].get("transition") or {}),
        },
        "configuration": {
            "template": answers["configuration"].get("template") or "",
            "inputs": list(answers["configuration"]["inputs"]),
        },
        "docker": {
            "compose_file": "compose/docker-compose.yml",
            "images": docker_images,
        },
        "database": dict(answers["database"]),
        "persistent_state": dict(answers["persistent_state"]),
        "offline_requirements": dict(answers["offline_requirements"]),
        "models": {"required": answers["models"]["required"], "artifacts": model_artifacts},
        "client": dict(answers["client"]),
        "verification": dict(answers["verification"]),
        "documentation": dict(answers["documentation"]),
        "integrity": {
            "checksum_algorithm": "sha256",
            "checksum_file": "checksums/SHA256SUMS",
        },
    }

    if git_facts.get("tag"):
        manifest["source"]["git_tag"] = git_facts["tag"]

    return manifest


def _now_iso8601() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
