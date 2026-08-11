"""Integrity closure — `checksums/SHA256SUMS` and the Release fingerprint.

RC-INT-002 names a minimum required coverage list (`release.yaml`,
artifacts, scripts, documentation, verification resources, the
Compliance Report) — this module checksums *every* real file in the
Release directory except `SHA256SUMS` itself, a conservative COMPLETED
superset: covering more than the minimum can't violate "every required
X is represented", and `compose/`/`configuration/`/`database/` content
deserves the same integrity protection even though the rule text doesn't
name them individually.

Format is plain `sha256sum`-compatible (`<hex>  <relative/posix/path>`,
two spaces, sorted by path) — an engineer can `cd` into a shipped Release
and run `sha256sum -c checksums/SHA256SUMS` for themselves, no Packager
needed.

The Release fingerprint has no formula given anywhere in the
architecture beyond its `sha256:...` display format (`4.7. Stage 4 —
Offline Platform Specification.md`, "hcat@1.1.0 / fingerprint:
sha256..."). COMPLETED here as the sha256 of `release.yaml`'s own raw
bytes — deliberately *not* derived from SHA256SUMS, which would create a
circular dependency: RC-INT-004's mandated closure order generates the
Compliance Report (which embeds the fingerprint) *before* the final
SHA256SUMS (which covers the Compliance Report). A manifest-content
fingerprint is fully computable at that point; full-content integrity
beyond the manifest is what SHA256SUMS itself (and RC-INT-002/003) is
for.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

CHECKSUM_FILE_RELATIVE_PATH = "checksums/SHA256SUMS"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_file_checksums(release_dir: Path) -> dict[str, str]:
    """{relative_posix_path: hex_digest} for every real file in the
    Release directory except SHA256SUMS itself (never lists itself).
    """
    checksums = {}
    for path in sorted(release_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(release_dir).as_posix()
        if relative == CHECKSUM_FILE_RELATIVE_PATH:
            continue
        checksums[relative] = _sha256_file(path)
    return checksums


def render_sha256sums(checksums: dict[str, str]) -> str:
    return "".join(f"{digest}  {path}\n" for path, digest in sorted(checksums.items()))


def write_checksums(release_dir: Path) -> Path:
    checksums = compute_file_checksums(release_dir)
    checksum_path = release_dir / CHECKSUM_FILE_RELATIVE_PATH
    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path.write_text(render_sha256sums(checksums), encoding="utf-8")
    return checksum_path


def compute_release_fingerprint(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def verify_checksums(release_dir: Path) -> list[str]:
    """Re-checksums the release directory and compares against the
    recorded SHA256SUMS. Returns a list of human-readable mismatch
    descriptions — empty means every recorded checksum still matches.
    """
    checksum_path = release_dir / CHECKSUM_FILE_RELATIVE_PATH
    if not checksum_path.is_file():
        return [f"{CHECKSUM_FILE_RELATIVE_PATH} does not exist"]

    recorded: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, relative = line.partition("  ")
        recorded[relative] = digest

    current = compute_file_checksums(release_dir)
    mismatches = []
    for relative, digest in sorted(recorded.items()):
        if relative not in current:
            mismatches.append(f"{relative}: recorded but missing")
        elif current[relative] != digest:
            mismatches.append(f"{relative}: checksum mismatch")
    for relative in sorted(set(current) - set(recorded)):
        mismatches.append(f"{relative}: present but not recorded in SHA256SUMS")
    return mismatches
