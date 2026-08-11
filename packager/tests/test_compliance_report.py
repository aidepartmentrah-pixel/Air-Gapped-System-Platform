import json
from pathlib import Path

from rah_packager.compliance_report import (
    COMPLIANCE_REPORT_SCHEMA,
    build_compliance_report,
    validate_compliance_report,
)

REAL_CONTRACT_SCHEMA_PATH = (
    Path(__file__).parent.parent.parent / "contracts" / "1.0" / "compliance-report.schema.json"
)


def _strip_metadata(node):
    if isinstance(node, dict):
        return {
            key: _strip_metadata(value)
            for key, value in node.items()
            if key not in ("$schema", "$id", "title", "description", "$comment")
        }
    if isinstance(node, list):
        return [_strip_metadata(item) for item in node]
    return node


def test_embedded_schema_matches_real_contract_file():
    real_schema = json.loads(REAL_CONTRACT_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert _strip_metadata(COMPLIANCE_REPORT_SCHEMA) == _strip_metadata(real_schema)


def test_build_compliance_report_all_pass_is_overall_pass():
    rule_results = [
        {"id": "RC-CON-001", "category": "RC-CON", "result": "PASS", "message": "ok"},
        {"id": "RC-DIR-001", "category": "RC-DIR", "result": "NOT_APPLICABLE", "message": "n/a"},
    ]

    report = build_compliance_report(
        application_slug="test-app",
        version="1.0.0",
        release_fingerprint="sha256:" + "a" * 64,
        generated_at="2026-01-01T00:00:00Z",
        rule_results=rule_results,
    )

    validate_compliance_report(report)  # must not raise
    assert report["overall_result"] == "PASS"
    assert report["summary"] == {
        "rules_executed": 2,
        "rules_passed": 1,
        "rules_failed": 0,
        "rules_not_applicable": 1,
        "rules_not_executed": 0,
    }


def test_build_compliance_report_any_fail_is_overall_fail():
    rule_results = [
        {"id": "RC-CON-001", "category": "RC-CON", "result": "PASS", "message": "ok"},
        {"id": "RC-ART-001", "category": "RC-ART", "result": "FAIL", "message": "missing archive"},
    ]

    report = build_compliance_report(
        application_slug="test-app",
        version="1.0.0",
        release_fingerprint="sha256:" + "a" * 64,
        generated_at="2026-01-01T00:00:00Z",
        rule_results=rule_results,
    )

    assert report["overall_result"] == "FAIL"
    assert report["summary"]["rules_failed"] == 1
