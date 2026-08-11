"""The Compliance Report (`compliance/release-compliance-report.json`) —
P7 Validation.

`COMPLIANCE_REPORT_SCHEMA` is transcribed verbatim from the real, frozen
`contracts/1.0/compliance-report.schema.json` — same "embed, don't read
the Contract file at runtime" choice P6 made for `RELEASE_MANIFEST_SCHEMA`,
verified against drift the same way
(`test_compliance_report.py::test_embedded_schema_matches_real_contract_file`).

`build_compliance_report()` takes the already-executed rule results (see
`compliance_rules.py`) and assembles the report exactly as the schema
requires: `overall_result` is `PASS` only if no rule result is `FAIL`
(`compliance_decision_rule` in `validation-rules.json` — every rule in
this Contract version is mandatory, no warning-level rules exist yet).
"""

from __future__ import annotations

import jsonschema

from rah_packager import __version__ as PACKAGER_VERSION
from rah_packager.errors import ComplianceReportSchemaError

CONTRACT_VERSION = "1.0"

# Verbatim transcription of contracts/1.0/compliance-report.schema.json.
COMPLIANCE_REPORT_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://rah-release-system/contracts/1.0/compliance-report.schema.json",
    "title": "RAH Release Compliance Report",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "contract_version",
        "validator_version",
        "generated_at",
        "release_identity",
        "validation_environment",
        "overall_result",
        "summary",
        "rules",
    ],
    "properties": {
        "contract_version": {"type": "string", "const": "1.0"},
        "generator_version": {"type": "string"},
        "validator_version": {"type": "string"},
        "generated_at": {"type": "string", "format": "date-time"},
        "release_identity": {
            "type": "object",
            "additionalProperties": False,
            "required": ["application_slug", "version", "release_fingerprint"],
            "properties": {
                "application_slug": {"type": "string"},
                "version": {"type": "string"},
                "release_fingerprint": {"type": "string"},
            },
        },
        "validation_environment": {"type": "string"},
        "overall_result": {"type": "string", "enum": ["PASS", "FAIL"]},
        "summary": {
            "type": "object",
            "additionalProperties": False,
            "required": ["rules_executed", "rules_passed", "rules_failed"],
            "properties": {
                "rules_executed": {"type": "integer", "minimum": 0},
                "rules_passed": {"type": "integer", "minimum": 0},
                "rules_failed": {"type": "integer", "minimum": 0},
                "rules_not_applicable": {"type": "integer", "minimum": 0},
                "rules_not_executed": {"type": "integer", "minimum": 0},
            },
        },
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "category", "result", "message"],
                "properties": {
                    "id": {"type": "string", "pattern": "^RC-[A-Z]{2,6}-[0-9]{3}$"},
                    "category": {"type": "string"},
                    "result": {
                        "type": "string",
                        "enum": ["PASS", "FAIL", "NOT_APPLICABLE", "NOT_EXECUTED"],
                    },
                    "message": {"type": "string"},
                },
            },
        },
    },
}


def validate_compliance_report(report: dict) -> None:
    try:
        jsonschema.validate(report, COMPLIANCE_REPORT_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ComplianceReportSchemaError(exc.message) from exc


def build_compliance_report(
    *,
    application_slug: str,
    version: str,
    release_fingerprint: str,
    generated_at: str,
    rule_results: list[dict],
) -> dict:
    """`rule_results`: list of `{"id", "category", "result", "message"}`,
    already produced by `compliance_rules.run_rules()`. Pure function —
    no filesystem access.
    """
    summary = {
        "rules_executed": len(rule_results),
        "rules_passed": sum(1 for r in rule_results if r["result"] == "PASS"),
        "rules_failed": sum(1 for r in rule_results if r["result"] == "FAIL"),
        "rules_not_applicable": sum(1 for r in rule_results if r["result"] == "NOT_APPLICABLE"),
        "rules_not_executed": sum(1 for r in rule_results if r["result"] == "NOT_EXECUTED"),
    }
    overall_result = "FAIL" if summary["rules_failed"] > 0 else "PASS"

    return {
        "contract_version": CONTRACT_VERSION,
        "validator_version": PACKAGER_VERSION,
        "generated_at": generated_at,
        "release_identity": {
            "application_slug": application_slug,
            "version": version,
            "release_fingerprint": release_fingerprint,
        },
        "validation_environment": f"rah-packager {PACKAGER_VERSION}",
        "overall_result": overall_result,
        "summary": summary,
        "rules": rule_results,
    }
