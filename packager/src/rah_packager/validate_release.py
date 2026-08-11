"""`rah validate` — standalone, read-only Release re-validation.

Distinct from `rah package`'s own internal stage-A check: this command
takes a Release *directory* directly (no source project required),
matching the CLI Contract's `rah validate --release <path>` shape and the
"Real Manual Acceptance Test" procedure's "Independent Validator PASS"
step — it has to work without the original source repository at hand,
since the whole point is proving the Release independently of the run
that produced it.

Runs every RC-* rule (stage-A + RC-INT; RC-REPRO is excluded everywhere,
see `compliance_rules.py`), plus a full `verify_checksums()` re-hash of
every file in the Release — stricter than RC-INT-003 alone (which only
re-checks `release.yaml`'s own checksum): this is the "Checksum Mismatch"
scenario's real detector, since a tampered *script* or *image archive*
should fail validation just as loudly as a tampered manifest.

`--project`, if given, supplies Project Version State for RC-MAN-002
(identity cross-check); without it, that one rule reports
`NOT_APPLICABLE` rather than being silently skipped.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from rah_packager.checksums import verify_checksums
from rah_packager.compliance_rules import run_integrity_rules, run_stage_a_rules
from rah_packager.errors import ReleaseNotFoundError
from rah_packager.project_state import project_state_path


def validate_release(
    release_path: str | os.PathLike,
    project_path: str | os.PathLike | None = None,
) -> dict:
    release_dir = Path(release_path)
    if not (release_dir / "release.yaml").is_file():
        raise ReleaseNotFoundError(str(release_dir))

    project_state = None
    if project_path is not None:
        state_path = project_state_path(Path(project_path))
        if state_path.is_file():
            project_state = json.loads(state_path.read_text(encoding="utf-8"))

    rule_results = run_stage_a_rules(release_dir, project_state) + run_integrity_rules(release_dir)
    checksum_mismatches = verify_checksums(release_dir)

    failed_rule_ids = [r["id"] for r in rule_results if r["result"] == "FAIL"]
    overall_result = "FAIL" if failed_rule_ids or checksum_mismatches else "PASS"

    return {
        "release_directory": str(release_dir),
        "overall_result": overall_result,
        "rules": rule_results,
        "checksum_mismatches": checksum_mismatches,
    }
