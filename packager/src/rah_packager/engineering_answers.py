"""Engineering Answers — P3's `.rah/engineering-answers.json`.

Unlike P1's Project Version State schema, nothing here was pre-drafted in
the frozen architecture (the proposal itself flags staleness as "one of
the weaker areas identified during architecture review"). This module is
that missing design, made concrete:

- `ENGINEERING_ANSWERS_SCHEMA` covers exactly the gap between what P2's
  `ProjectInspectionResult` already determines and what the real, frozen
  Release Manifest schema (`contracts/1.0/release-manifest.schema.json`)
  requires. Every section below is derived from that manifest schema, not
  invented in parallel — `compatibility`, `configuration.inputs`,
  `database`, `persistent_state`, `offline_requirements`, `client`, and
  `verification` are structurally identical to their manifest counterparts,
  because engineering answers exist to eventually populate those exact
  fields. `application`/`release`/`source`/`docker`/`integrity` are
  excluded here because P2 (or later generated-at-packaging-time logic)
  already supplies them deterministically. `models.artifacts[]` drops
  `baked_into_image`/`checksum` for the same reason — both are computed at
  packaging time (P6), not answerable during engineering.
- Same structural/cross-field split the manifest schema itself already
  uses: this schema validates shape and types only. Cross-field and
  conditional rules (e.g. "if database.required is true, platform must be
  present") are deliberately NOT encoded here — see
  docs/decisions/engineering-answers-and-staleness.md.
- `compute_inspection_fingerprint()` is the staleness anchor: a sha256 of
  the canonicalized `ProjectInspectionResult`, recorded in `based_on` at
  `prepare-answers` time and re-checked at `validate-answers` time against
  the *current* repo state.
"""

from __future__ import annotations

import hashlib
import json

import jsonschema

from rah_packager.errors import EngineeringAnswersSchemaError

SCHEMA_VERSION = "1.0"

# Verbatim, structurally, from contracts/1.0/release-manifest.schema.json —
# see this module's docstring for which sections and why.
ENGINEERING_ANSWERS_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://rah.local/schemas/engineering-answers.schema.json",
    "title": "RAH Engineering Answers",
    "description": (
        "Structural/type schema only — cross-field, conditional, and staleness "
        "rules are deliberately NOT encoded here, the same split the Release "
        "Manifest schema itself already uses. Those live in `rah validate-answers`'s "
        "application-level checks instead."
    ),
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "based_on",
        "application",
        "compatibility",
        "deployment",
        "configuration",
        "database",
        "persistent_state",
        "offline_requirements",
        "models",
        "client",
        "verification",
        "documentation",
    ],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "based_on": {
            "type": "object",
            "additionalProperties": False,
            "required": ["git_commit", "inspection_fingerprint"],
            "properties": {
                "git_commit": {"type": "string", "pattern": "^[0-9a-fA-F]{40}$"},
                "inspection_fingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "description": (
                "The staleness anchor. Recomputed and compared against the current "
                "repo at `validate-answers` time — see compute_inspection_fingerprint()."
            ),
        },
        "application": {
            "type": "object",
            "additionalProperties": False,
            "required": ["description"],
            "properties": {"description": {"type": "string", "minLength": 1}},
        },
        "compatibility": {
            "type": "object",
            "additionalProperties": False,
            "required": ["minimum_rah_oip_version", "supported_architectures"],
            "properties": {
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
            "required": ["entrypoints", "supported_operations"],
            "properties": {
                "compose_project_name": {"type": ["string", "null"]},
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
                        "update": {"type": "boolean"},
                        "downgrade": {"type": "boolean"},
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
            "required": ["inputs"],
            "properties": {
                "template": {"type": ["string", "null"]},
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
            "description": (
                "When required=false, platform/deployment_mode/etc. are omitted "
                "rather than null — matches the manifest schema's own convention."
            ),
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
                "public_internet_required": {"type": "boolean"},
                "public_registry_required": {"type": "boolean"},
                "public_cdn_required": {"type": "boolean"},
                "online_model_registry_required": {"type": "boolean"},
            },
            "description": "Shall normally all be false — same Contract norm as the manifest.",
        },
        "models": {
            "type": "object",
            "additionalProperties": False,
            "required": ["required"],
            "properties": {
                "required": {"type": "boolean"},
                "artifacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "version"],
                        "properties": {
                            "id": {"type": "string"},
                            "version": {"type": "string"},
                            "source_registry": {"type": "string"},
                        },
                    },
                    "description": (
                        "baked_into_image and checksum are dropped here — both are "
                        "computed at packaging time (P6), not answerable during engineering."
                    ),
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
            "required": ["required_checks"],
            "properties": {
                "entrypoint": {"type": ["string", "null"]},
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
    },
}


def compute_inspection_fingerprint(inspection_result: dict) -> str:
    """sha256 of the canonicalized `ProjectInspectionResult` — deterministic
    regardless of key order, since `sort_keys=True` normalizes it.
    """
    canonical = json.dumps(inspection_result, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_engineering_answers_schema(answers: dict) -> None:
    """Structural validation only — see this module's docstring for why
    cross-field and staleness checks live elsewhere (`rah validate-answers`).
    """
    try:
        jsonschema.validate(answers, ENGINEERING_ANSWERS_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise EngineeringAnswersSchemaError(exc.message) from exc
