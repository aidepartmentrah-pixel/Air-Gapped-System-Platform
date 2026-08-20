import pytest

from rah_packager.engineering_answers import (
    compute_inspection_fingerprint,
    validate_engineering_answers_schema,
)
from rah_packager.errors import EngineeringAnswersSchemaError


def _valid_answers() -> dict:
    return {
        "schema_version": "1.0",
        "based_on": {
            "git_commit": "a" * 40,
            "inspection_fingerprint": "b" * 64,
        },
        "application": {"description": "A hospital application that does X."},
        "compatibility": {
            "minimum_rah_oip_version": "1.0",
            "supported_architectures": ["amd64"],
            "required_shared_services": [],
        },
        "deployment": {
            "entrypoints": {
                "install": "scripts/install_offline.sh",
                "verify": "scripts/verify_installation.sh",
            },
            "supported_operations": {"fresh_install": True, "update": True},
        },
        "configuration": {
            "template": ".env.example",
            "inputs": [
                {
                    "key": "DATABASE_PASSWORD",
                    "label": "Database password",
                    "type": "password",
                    "required": True,
                    "source": "generated",
                    "secret": True,
                }
            ],
        },
        "database": {
            "required": True,
            "platform": "sqlserver",
            "deployment_mode": "application_managed",
        },
        "persistent_state": {
            "preserve_during_update": ["database_data", "generated_credentials"],
        },
        "offline_requirements": {
            "public_internet_required": False,
            "public_registry_required": False,
            "public_cdn_required": False,
            "online_model_registry_required": False,
        },
        "models": {"required": False},
        "client": {"preparation_required": False, "https_required": False},
        "verification": {
            "entrypoint": "scripts/verify_installation.sh",
            "required_checks": [],
        },
        "documentation": {
            "release_notes": "release/documentation/RELEASE_NOTES.md",
            "installation": "release/documentation/INSTALL_OFFLINE.md",
            "update": "release/documentation/UPDATE_OFFLINE.md",
            "recovery": "release/documentation/BACKUP_RESTORE.md",
            "known_issues": "release/documentation/TROUBLESHOOTING.md",
        },
    }


# --- Schema validation ---


def test_valid_answers_pass_schema_validation():
    validate_engineering_answers_schema(_valid_answers())  # must not raise


def test_missing_required_section_is_rejected():
    answers = _valid_answers()
    del answers["database"]

    with pytest.raises(EngineeringAnswersSchemaError) as exc_info:
        validate_engineering_answers_schema(answers)
    assert exc_info.value.code == "PKG-ENGINEERING-ANSWERS-SCHEMA-INVALID"


def test_wrong_type_is_rejected():
    answers = _valid_answers()
    answers["client"]["https_required"] = "yes"  # should be a bool

    with pytest.raises(EngineeringAnswersSchemaError):
        validate_engineering_answers_schema(answers)


def test_invalid_enum_value_is_rejected():
    answers = _valid_answers()
    answers["database"]["platform"] = "oracle"  # not in the allowed enum

    with pytest.raises(EngineeringAnswersSchemaError):
        validate_engineering_answers_schema(answers)


def test_unknown_top_level_field_is_rejected():
    answers = _valid_answers()
    answers["something_unexpected"] = True

    with pytest.raises(EngineeringAnswersSchemaError):
        validate_engineering_answers_schema(answers)


def test_malformed_git_commit_is_rejected():
    answers = _valid_answers()
    answers["based_on"]["git_commit"] = "not-a-real-commit-hash"

    with pytest.raises(EngineeringAnswersSchemaError):
        validate_engineering_answers_schema(answers)


# --- Staleness fingerprint ---


def test_fingerprint_is_deterministic_for_identical_input():
    inspection_result = {"git": {"commit": "abc"}, "docker": {"services": []}}

    assert compute_inspection_fingerprint(inspection_result) == compute_inspection_fingerprint(
        inspection_result
    )


def test_fingerprint_ignores_key_order():
    a = {"git": {"commit": "abc"}, "docker": {"services": []}}
    b = {"docker": {"services": []}, "git": {"commit": "abc"}}

    assert compute_inspection_fingerprint(a) == compute_inspection_fingerprint(b)


def test_fingerprint_changes_when_content_changes():
    a = {"git": {"commit": "abc"}}
    b = {"git": {"commit": "def"}}

    assert compute_inspection_fingerprint(a) != compute_inspection_fingerprint(b)


def test_fingerprint_is_a_sha256_hex_digest():
    fingerprint = compute_inspection_fingerprint({"anything": True})

    assert len(fingerprint) == 64
    assert all(c in "0123456789abcdef" for c in fingerprint)


def test_fingerprint_ignores_packager_state_changes():
    """A successful `rah package` run mutates `.rah/project-state.json`
    (new `release_history` entry), which flows into the next inspection's
    `packager_state` category. That must not itself count as staleness —
    otherwise every successful Release would invalidate its own
    just-used engineering answers for the very next run.
    """
    before = {
        "git": {"commit": "abc"},
        "packager_state": None,
    }
    after = {
        "git": {"commit": "abc"},
        "packager_state": {
            "current_release": "1.0.0",
            "release_history": [{"version": "1.0.0"}],
        },
    }

    assert compute_inspection_fingerprint(before) == compute_inspection_fingerprint(after)
