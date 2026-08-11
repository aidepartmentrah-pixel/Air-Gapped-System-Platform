"""`rah package` — P7 Finalization. The Period A Packager finish line:
turns a P6 candidate into a finalized Release and proves it independently.

Orchestration, in order (RC-INT-004's mandated closure sequence):

1. `rah plan`'s own gates (P4, reused unchanged) — dirty state, duplicate
   version, missing/stale answers. Cheap, runs before anything expensive.
2. Refuse silently overwriting an **already-finalized** Release — checked
   *before* calling `construct_release()`, which would otherwise
   unconditionally `rmtree` the target directory (P6's own confirmed
   "candidate" overwrite semantics do not apply once a Release is real).
3. `construct_release()` (P6) — the real, expensive Docker build.
4. Stage-A compliance checks (`compliance_rules.run_stage_a_rules`) —
   every RC-* rule except RC-INT (integrity closure hasn't happened yet,
   RC-INT can't be meaningful before it does) and RC-REPRO (a build-time
   regression check, not a per-Release rule). Any FAIL aborts here —
   Project Version State is untouched (Finalization Atomicity).
5. Integrity closure, exactly as RC-INT-004 specifies: compute the
   Release fingerprint (sha256 of `release.yaml`'s own bytes — see
   `checksums.py`'s docstring for why it isn't derived from SHA256SUMS),
   build and write the Compliance Report, generate the final SHA256SUMS
   (which therefore covers the just-written report), self-verify it.
6. Only now — after every prior step succeeded — append to Project
   Version State's `release_history` and set `current_release`.

`overall_result: "FAIL"` in a *written* Compliance Report never happens
in this flow: a FAIL is raised as `ReleaseComplianceFailedError` before
any report is written at all (release-layout.yaml: "A FAILED validation
run's report is not guaranteed to live here — only a successful (PASS)
Compliance Report becomes part of the immutable, frozen Release").
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from rah_packager.checksums import compute_release_fingerprint, verify_checksums, write_checksums
from rah_packager.compliance_report import build_compliance_report, validate_compliance_report
from rah_packager.compliance_rules import run_stage_a_rules
from rah_packager.construct_release import construct_release
from rah_packager.errors import (
    ReleaseAlreadyExistsError,
    ReleaseComplianceFailedError,
    ReleaseFinalizationWriteError,
)
from rah_packager.project_state import project_state_path, validate_state, write_state_atomically
from rah_packager.release_plan import prepare_plan

COMPLIANCE_REPORT_RELATIVE_PATH = "compliance/release-compliance-report.json"


def _now_iso8601() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_project_state(project_path: Path) -> dict:
    return json.loads(project_state_path(project_path).read_text(encoding="utf-8"))


def _append_release_history(project_path: Path, manifest: dict, generated_at: str, summary: str) -> None:
    state_path = project_state_path(project_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    version = manifest["release"]["version"]

    state["versioning"]["current_release"] = version
    state["versioning"]["next_version"] = version
    state["release_history"].append(
        {
            "version": version,
            "created_at": generated_at,
            "source": {
                "git_commit": manifest["source"]["git_commit"],
                "git_tag": manifest["source"].get("git_tag"),
            },
            "summary": summary,
        }
    )
    validate_state(state)  # defensive, same discipline as P1's own writer
    write_state_atomically(state_path, state)


def package_release(
    project_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    increment: str = "patch",
    answers_path: str | os.PathLike | None = None,
    summary: str | None = None,
) -> dict:
    plan = prepare_plan(project_path, increment, answers_path)  # every P1/P3/P4 gate

    path = Path(project_path)
    release_dir = Path(output_dir) / plan["release_directory_name"]

    if (release_dir / COMPLIANCE_REPORT_RELATIVE_PATH).is_file():
        raise ReleaseAlreadyExistsError(str(release_dir))

    construct_result = construct_release(path, output_dir, increment, answers_path, summary)

    project_state = _read_project_state(path)
    rule_results = run_stage_a_rules(release_dir, project_state)
    failed_rules = [r for r in rule_results if r["result"] == "FAIL"]
    if failed_rules:
        raise ReleaseComplianceFailedError(failed_rules)

    manifest_bytes = (release_dir / "release.yaml").read_bytes()
    fingerprint = compute_release_fingerprint(manifest_bytes)
    generated_at = _now_iso8601()

    report = build_compliance_report(
        application_slug=plan["application"]["slug"],
        version=plan["proposed_version"],
        release_fingerprint=fingerprint,
        generated_at=generated_at,
        rule_results=rule_results,
    )
    validate_compliance_report(report)  # defensive — the Packager built it

    report_path = release_dir / COMPLIANCE_REPORT_RELATIVE_PATH
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        checksum_path = write_checksums(release_dir)
    except OSError as exc:
        raise ReleaseFinalizationWriteError(str(exc)) from exc

    mismatches = verify_checksums(release_dir)
    if mismatches:
        raise ReleaseFinalizationWriteError(
            f"final checksum self-verification failed: {'; '.join(mismatches)}"
        )

    manifest = yaml.safe_load(manifest_bytes.decode("utf-8"))
    _append_release_history(
        path, manifest, generated_at, summary or f"{plan['application']['name']} {plan['proposed_version']}"
    )

    return {
        "release_directory": construct_result["release_directory"],
        "manifest_path": construct_result["manifest_path"],
        "compliance_report_path": str(report_path),
        "checksum_path": str(checksum_path),
        "release_fingerprint": fingerprint,
        "application": plan["application"],
        "version": plan["proposed_version"],
        "overall_result": report["overall_result"],
        "images": construct_result["images"],
    }
