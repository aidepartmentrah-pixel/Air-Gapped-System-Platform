"""Model artifact resolution — computing a checksum from the source model
file(s) at packaging time and associating each declared artifact with the
Docker image/service it's baked into.

Split into two passes because the two things it computes become knowable at
different points in `construct_release.py`'s flow:

- `verify_and_checksum_model_artifacts()` runs before the real Docker
  build — fail fast on a missing source file rather than after burning
  minutes building images, matching this project's established ordering
  discipline (every other cheap gate in construct_release.py already runs
  before build_release_images()). Matches the frozen Contract's own
  wording for `checksum`: "computed... at packaging time, before the
  Docker build."
- `resolve_baked_into_image()` runs after the build, once the real
  docker.images[] list — and therefore which services actually got a real
  exported archive — is known. Declaring `baked_into_image` before that
  would be claiming an association with an image that might not exist.

`source_path`/`service` are answers-only fields (see engineering_answers.py)
— never part of the frozen Release Manifest's `models.artifacts[]` shape
(additionalProperties: false there — contracts/1.0/release-manifest.schema.json),
so both are dropped from the final per-artifact dict this module hands back.

Deliberately real filesystem I/O — not part of build_release_manifest's own
"pure function, no filesystem access" contract (release_manifest.py). Called
from construct_release.py's orchestration instead, the same tier as
build_release_images().
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from rah_packager.errors import ModelServiceNotBuiltError, ModelSourcePathNotFoundError


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_checksum(root: Path) -> str:
    # Deterministic regardless of filesystem iteration order: hash a sorted
    # manifest of "relative/path:sha256\n" for every file under root, not
    # directory metadata (mtimes, inode order), which isn't reproducible.
    entries = [
        f"{file_path.relative_to(root).as_posix()}:{_file_checksum(file_path)}"
        for file_path in sorted(p for p in root.rglob("*") if p.is_file())
    ]
    manifest = "\n".join(entries).encode("utf-8")
    return hashlib.sha256(manifest).hexdigest()


def _compute_checksum(source_path: Path) -> str:
    # A single file is just the trivial one-entry case of the tree
    # algorithm, but hashing the file's own bytes directly (rather than a
    # one-line manifest referencing it) keeps the common case's checksum
    # independent of the artifact's declared id/path spelling.
    if source_path.is_dir():
        return f"sha256:{_tree_checksum(source_path)}"
    return f"sha256:{_file_checksum(source_path)}"


def verify_and_checksum_model_artifacts(project_path: Path, answers: dict) -> list[dict]:
    """For each declared model artifact: verify `source_path` exists,
    compute its checksum. Returns each artifact's `id`/`version`/`service`/
    `checksum` (plus `source_registry` if declared) — `service` is carried
    through for `resolve_baked_into_image()` to consume once the real
    Docker build result is known; `source_path` itself is not carried
    through, since its only job (locating the file to hash) is done.
    """
    resolved = []
    for artifact in answers["models"].get("artifacts") or []:
        source_path = Path(project_path) / artifact["source_path"]
        if not source_path.exists():
            raise ModelSourcePathNotFoundError(artifact["id"], artifact["source_path"])
        entry = {
            "id": artifact["id"],
            "version": artifact["version"],
            "service": artifact["service"],
            "checksum": _compute_checksum(source_path),
        }
        if artifact.get("source_registry"):
            entry["source_registry"] = artifact["source_registry"]
        resolved.append(entry)
    return resolved


def resolve_baked_into_image(model_artifacts: list[dict], docker_images: list[dict]) -> list[dict]:
    """Cross-checks each artifact's `service` against the real, actually
    exported docker.images[] list and finalizes the manifest-shaped
    artifact dict — `service` is replaced with `baked_into_image`, matching
    the frozen manifest schema exactly (additionalProperties: false there;
    `service` itself is never a manifest field).
    """
    built_services = {image["service"] for image in docker_images}
    finalized = []
    for artifact in model_artifacts:
        service = artifact["service"]
        if service not in built_services:
            raise ModelServiceNotBuiltError(artifact["id"], service)
        entry = {key: value for key, value in artifact.items() if key != "service"}
        entry["baked_into_image"] = service
        finalized.append(entry)
    return finalized
