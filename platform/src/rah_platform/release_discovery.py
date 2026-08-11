"""Release Discovery — PL2.

Scans the configured incoming Release Storage directory and classifies
each candidate directory found there. Per the plan and architecture §3.4,
scanning performs only the minimum parsing needed for identity and basic
readiness — it does not validate the full Manifest schema, verify the
Compliance Report, or check checksums (that's `PL3`'s `import_release`
job) and it never registers an Application or Release.

**Classification heuristic** (engineering judgment — PL2's own scope,
not the full Contract structural validation in
`contracts/1.0/release-layout.yaml`, which belongs to the Release
Validator/PL3):

- No `release.yaml` present:
    - some other Contract-reserved structure exists (`compose/`,
      `docker-images/`, `scripts/`, `configuration/`, `database/`,
      `documentation/`, `verification/`, `checksums/`, `compliance/`) →
      `INVALID_MANIFEST` — the manifest specifically is the problem.
    - otherwise (nothing recognizable present) → `INCOMPLETE` — this
      looks like a transfer that barely started.
- `release.yaml` present but fails to parse as YAML, or parses but is
  missing `application.slug`/`application.name`/`release.version` →
  `INVALID_MANIFEST`.
- `release.yaml` present and parses with a full identity, but
  `checksums/SHA256SUMS` is absent → `INCOMPLETE`. The Release Contract
  itself generates `SHA256SUMS` last during finalization (see
  `release-layout.yaml`'s notes on `checksums/`), so its absence is a
  reasonable, if approximate, "this transfer hasn't finished" signal.
- `release.yaml` present, valid, identity complete, `checksums/SHA256SUMS`
  present → `READY_FOR_IMPORT`.

`ALREADY_IMPORTED` and `IDENTITY_CONFLICT` are cross-checked against the
real Release Registry (`applications`/`releases`) as of `PL3` — see
`_check_registry_state` below. They were not reachable from PL2 alone
(no Registry existed yet); this closes that gap now that `PL3` creates
one, without needing to revisit PL2's own already-reviewed scope.
`PREVIOUSLY_REJECTED` remains unreachable — nothing in the plan tracks
rejected-candidate history yet.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
import yaml

from rah_platform.errors import CandidateNotFoundError, ReleaseStorageUnavailableError
from rah_platform.models import applications, release_candidates, releases


def compute_fingerprint(candidate_path: str) -> str:
    """The Release fingerprint — sha256 of the manifest file's raw bytes.
    Canonical definition lives here since both scanning (to recognize an
    already-imported candidate) and import (`PL3`'s `release_import.py`)
    need the identical computation.
    """
    return hashlib.sha256((Path(candidate_path) / "release.yaml").read_bytes()).hexdigest()

_RESERVED_STRUCTURE_ENTRIES = {
    "compose",
    "docker-images",
    "scripts",
    "configuration",
    "database",
    "documentation",
    "verification",
    "checksums",
    "compliance",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_identity(candidate_path: str) -> tuple[dict | None, list[str]]:
    """Returns (identity, issues). `identity` is None when the manifest is
    missing, unparseable, or incomplete.
    """
    manifest_path = os.path.join(candidate_path, "release.yaml")
    if not os.path.isfile(manifest_path):
        return None, ["release.yaml is missing"]

    try:
        with open(manifest_path, encoding="utf-8") as f:
            parsed = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        return None, [f"release.yaml is not valid YAML: {exc}"]

    if not isinstance(parsed, dict):
        return None, ["release.yaml did not parse to a mapping"]

    application = parsed.get("application") or {}
    release = parsed.get("release") or {}
    slug = application.get("slug")
    name = application.get("name")
    version = release.get("version")

    missing = [
        field
        for field, value in (
            ("application.slug", slug),
            ("application.name", name),
            ("release.version", version),
        )
        if not value
    ]
    if missing:
        return None, [f"release.yaml is missing required field(s): {', '.join(missing)}"]

    return {"slug": slug, "name": name, "version": version}, []


def _has_reserved_structure(candidate_path: str) -> bool:
    try:
        entries = set(os.listdir(candidate_path))
    except OSError:
        return False
    return bool(entries & _RESERVED_STRUCTURE_ENTRIES)


def _classify(candidate_path: str) -> tuple[str, dict | None, list[str]]:
    identity, issues = _read_identity(candidate_path)

    if identity is None:
        if issues == ["release.yaml is missing"] and not _has_reserved_structure(candidate_path):
            return "INCOMPLETE", None, issues
        return "INVALID_MANIFEST", None, issues

    checksums_path = os.path.join(candidate_path, "checksums", "SHA256SUMS")
    if not os.path.isfile(checksums_path):
        return "INCOMPLETE", identity, ["checksums/SHA256SUMS is missing — transfer may be incomplete"]

    return "READY_FOR_IMPORT", identity, []


def _check_registry_state(conn, identity: dict, fingerprint: str) -> str | None:
    """Cross-checks a structurally-ready candidate against the real
    Release Registry. Returns `"ALREADY_IMPORTED"` (same application,
    version, and content already imported), `"IDENTITY_CONFLICT"` (same
    application and version, different content — a real conflict, not
    just a duplicate), or `None` (genuinely new).
    """
    existing_fingerprint = conn.execute(
        sa.select(releases.c.fingerprint)
        .select_from(releases.join(applications, releases.c.application_id == applications.c.application_id))
        .where(applications.c.slug == identity["slug"], releases.c.version == identity["version"])
    ).scalar()
    if existing_fingerprint is None:
        return None
    return "ALREADY_IMPORTED" if existing_fingerprint == fingerprint else "IDENTITY_CONFLICT"


def scan_releases(engine, incoming_directory: str) -> dict:
    """Read-only per §3.4/§3.5: never touches the Operation Framework,
    never creates an Application or Release. Upserts `release_candidates`
    keyed by `directory_name` so a repeat scan of the same physical
    directory updates the existing row instead of creating a duplicate.
    """
    if not os.path.isdir(incoming_directory):
        raise ReleaseStorageUnavailableError(
            "The configured Release Storage incoming directory does not exist or is not a directory.",
            stage="SCANNING",
            details={"incoming_directory": incoming_directory},
        )

    try:
        entries = sorted(os.listdir(incoming_directory))
    except OSError as exc:
        raise ReleaseStorageUnavailableError(
            "The configured Release Storage incoming directory is not readable.",
            stage="SCANNING",
            details={"incoming_directory": incoming_directory, "reason": str(exc)},
        ) from exc

    directory_names = [
        name for name in entries if os.path.isdir(os.path.join(incoming_directory, name))
    ]

    now = _now()
    candidates = []
    with engine.begin() as conn:
        for directory_name in directory_names:
            candidate_path = os.path.join(incoming_directory, directory_name)
            discovery_state, identity, issues = _classify(candidate_path)

            already_imported = False
            if discovery_state == "READY_FOR_IMPORT":
                fingerprint = compute_fingerprint(candidate_path)
                registry_state = _check_registry_state(conn, identity, fingerprint)
                if registry_state == "ALREADY_IMPORTED":
                    discovery_state = "ALREADY_IMPORTED"
                    already_imported = True
                elif registry_state == "IDENTITY_CONFLICT":
                    discovery_state = "IDENTITY_CONFLICT"
                    issues = [
                        f"Same application+version already imported with different content (fingerprint {fingerprint[:12]}...)."
                    ]

            existing = conn.execute(
                sa.select(release_candidates.c.candidate_id, release_candidates.c.first_seen_at).where(
                    release_candidates.c.directory_name == directory_name
                )
            ).mappings().first()

            candidate_id = existing["candidate_id"] if existing else str(uuid.uuid4())
            first_seen_at = existing["first_seen_at"] if existing else now

            values = {
                "candidate_id": candidate_id,
                "directory_name": directory_name,
                "application_slug": identity["slug"] if identity else None,
                "release_version": identity["version"] if identity else None,
                "discovery_state": discovery_state,
                "already_imported": already_imported,
                "issues": issues,
                "first_seen_at": first_seen_at,
                "last_scanned_at": now,
            }

            if existing:
                conn.execute(
                    release_candidates.update()
                    .where(release_candidates.c.candidate_id == candidate_id)
                    .values(**{k: v for k, v in values.items() if k != "candidate_id"})
                )
            else:
                conn.execute(release_candidates.insert().values(**values))

            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "directory_name": directory_name,
                    "application_slug": values["application_slug"],
                    "release_version": values["release_version"],
                    "discovery_state": discovery_state,
                    "already_imported": already_imported,
                    "issues": issues,
                }
            )

    return {
        "scan_id": str(uuid.uuid4()),
        "incoming_directory": incoming_directory,
        "scanned_at": now.isoformat(),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _row_to_result(row) -> dict:
    return {
        "candidate_id": row["candidate_id"],
        "directory_name": row["directory_name"],
        "application_slug": row["application_slug"],
        "release_version": row["release_version"],
        "discovery_state": row["discovery_state"],
        "already_imported": row["already_imported"],
        "issues": row["issues"] or [],
        "first_seen_at": row["first_seen_at"].isoformat(),
        "last_scanned_at": row["last_scanned_at"].isoformat(),
    }


def list_candidates(engine) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(
            release_candidates.select().order_by(release_candidates.c.directory_name)
        ).mappings().all()
    return {"items": [_row_to_result(r) for r in rows]}


def get_candidate(engine, candidate_id: str) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            release_candidates.select().where(release_candidates.c.candidate_id == candidate_id)
        ).mappings().first()
    if row is None:
        raise CandidateNotFoundError(
            "No release candidate exists with the given candidate_id.",
            details={"candidate_id": candidate_id},
        )
    return _row_to_result(row)
