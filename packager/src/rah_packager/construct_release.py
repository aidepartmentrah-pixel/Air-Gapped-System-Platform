"""`rah construct` — P6 Release Construction.

"Where previous pieces finally combine": assembles a temporary candidate
Release directory (per `release-layout.yaml`) from everything P1–P5
already produce. Produces a *candidate*, not a finalized Release — no
checksums, no Compliance Report, no Project Version State update. Those
are P7's job entirely (`checksums/` and `compliance/` are "generated,
not authored", per the layout Contract, and generation happens during
*validation*, which P6 deliberately does not perform).

Re-run behavior: unconditional overwrite, same precedent as
`rah prepare-answers` — a candidate is explicitly not-yet-final, so
re-running construction for the same target version is a normal
workflow, not something to refuse. Any pre-existing directory at the
computed Release path is removed first, so a re-run never leaves stale
content from a prior attempt mixed in with fresh output.

Orchestration order matters: every cheap validation gate (`rah plan`'s
own gates, plus `check_answers_sufficient_for_manifest`) runs *before*
the expensive real Docker build — a bad engineering-answers input should
never cost the minutes a real multi-service build takes.

Known, deliberate scope gaps (not silently papered over):
- `docker.images[]` only includes services P5 actually built. A service
  with only a prebuilt `image:` reference (no `build:` key) has no
  exported archive in this Packager version and is not represented in
  the manifest at all — see `docker_build.py`'s own scope note.
- Model artifacts: `PKG-RELEASE-MODELS-NOT-SUPPORTED` if any are
  declared — see `release_manifest.py`.
- Script/documentation/verification file destinations flatten to
  basename (`scripts/{basename}`, not the original source-relative
  path) — matches the layout Contract's own "relative paths under
  scripts/" convention, but means two declared resources sharing a
  basename from different source directories would collide. Not
  resolved here; no real acceptance app has hit this.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path

import yaml

from rah_packager.docker_build import build_release_images
from rah_packager.errors import ReleaseConstructionWriteError
from rah_packager.inspection import inspect_project
from rah_packager.release_manifest import (
    build_release_manifest,
    check_answers_sufficient_for_manifest,
    validate_release_manifest,
)
from rah_packager.release_plan import prepare_plan
from rah_packager.validate_answers import default_answers_path

# (answers path, destination subdirectory under the Release root) — fixed
# by the layout Contract's own conventions, not something that needs to
# grow dynamically. database.* entries are added conditionally, only
# when database.required is true.
_SCRIPT_LIKE_FIELDS: list[tuple[tuple[str, ...], str]] = [
    (("deployment", "entrypoints", "install"), "scripts"),
    (("deployment", "entrypoints", "update"), "scripts"),
    (("deployment", "entrypoints", "verify"), "scripts"),
    (("deployment", "entrypoints", "backup"), "scripts"),
    (("deployment", "entrypoints", "restore"), "scripts"),
    (("verification", "entrypoint"), "verification"),
]

# initialization/migration live under database/; backup_before_update/
# recovery live under scripts/ — matches the one concrete example in the
# architecture's own manifest section verbatim (§18/§19 next to each
# other), not invented in parallel.
_DATABASE_FIELDS: list[tuple[tuple[str, ...], str]] = [
    (("database", "initialization", "entrypoint"), "database"),
    (("database", "migration", "entrypoint"), "database"),
    (("database", "backup_before_update", "entrypoint"), "scripts"),
    (("database", "recovery", "entrypoint"), "scripts"),
]

_DOCUMENTATION_FIELDS: list[tuple[tuple[str, ...], str]] = [
    (("documentation", "release_notes"), "documentation"),
    (("documentation", "installation"), "documentation"),
    (("documentation", "update"), "documentation"),
    (("documentation", "recovery"), "documentation"),
    (("documentation", "known_issues"), "documentation"),
]


def _dig(node: dict, path: tuple[str, ...]):
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _set_nested(node: dict, path: tuple[str, ...], value) -> None:
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def _copy_resources_and_rewrite_answers(
    project_path: Path, release_dir: Path, answers: dict
) -> dict:
    release_answers = copy.deepcopy(answers)

    fields = list(_SCRIPT_LIKE_FIELDS)
    if answers["database"]["required"]:
        fields += _DATABASE_FIELDS
    fields += _DOCUMENTATION_FIELDS
    if answers["configuration"].get("template"):
        fields.append((("configuration", "template"), "configuration"))

    for field_path, subdir in fields:
        source_relative = _dig(answers, field_path)
        if not source_relative:
            continue
        dest_relative = f"{subdir}/{Path(source_relative).name}"
        dest_path = release_dir / dest_relative
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists():
                shutil.copy2(project_path / source_relative, dest_path)
        except OSError as exc:
            raise ReleaseConstructionWriteError(str(exc)) from exc
        _set_nested(release_answers, field_path, dest_relative)

    return release_answers


def _write_compose_file(project_path: Path, release_dir: Path, docker_facts: dict, build_result: dict) -> str:
    compose_file = docker_facts.get("compose_file")
    compose_data = (
        yaml.safe_load((project_path / compose_file).read_text(encoding="utf-8")) or {}
        if compose_file
        else {}
    )
    services = compose_data.get("services") or {}
    built_by_service = {img["service"]: img for img in build_result["images"] if img["built"]}

    for name, definition in services.items():
        built = built_by_service.get(name)
        if built is None:
            continue
        definition.pop("build", None)
        definition["image"] = built["image"]

    dest_path = release_dir / "compose" / "docker-compose.yml"
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(yaml.safe_dump(compose_data, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        raise ReleaseConstructionWriteError(str(exc)) from exc

    return "compose/docker-compose.yml"


def _write_manifest_atomically(release_dir: Path, manifest: dict) -> Path:
    manifest_path = release_dir / "release.yaml"
    tmp_path = manifest_path.with_name(manifest_path.name + ".tmp")
    payload = yaml.safe_dump(manifest, sort_keys=True)
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        validate_release_manifest(yaml.safe_load(tmp_path.read_text(encoding="utf-8")))
        os.replace(tmp_path, manifest_path)
    except OSError as exc:
        raise ReleaseConstructionWriteError(str(exc)) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return manifest_path


def construct_release(
    project_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    increment: str = "patch",
    answers_path: str | os.PathLike | None = None,
    summary: str | None = None,
) -> dict:
    plan = prepare_plan(project_path, increment, answers_path)  # every P1/P3/P4 gate

    path = Path(project_path)
    resolved_answers_path = Path(answers_path) if answers_path else default_answers_path(path)
    answers = json.loads(resolved_answers_path.read_text(encoding="utf-8"))

    # Fail fast, before any expensive Docker build.
    check_answers_sufficient_for_manifest(answers)

    inspection_result = inspect_project(path)
    application = plan["application"]
    version = plan["proposed_version"]
    release_dir = Path(output_dir) / plan["release_directory_name"]

    if release_dir.exists():
        shutil.rmtree(release_dir)

    # Every layout-required directory exists from the start, even ones
    # this slice never populates (checksums/, compliance/ — P7's job) —
    # RC-DIR-003 checks for their presence regardless of finalization
    # state, and configuration/ is unconditionally required by the
    # layout Contract even when this app has no template to copy into it.
    mandatory_dirs = [
        "compose", "docker-images", "scripts", "configuration",
        "documentation", "verification", "checksums", "compliance",
    ]
    if answers["database"]["required"]:
        mandatory_dirs.append("database")
    for dirname in mandatory_dirs:
        (release_dir / dirname).mkdir(parents=True, exist_ok=True)

    build_result = build_release_images(path, application["slug"], version, release_dir)
    docker_images = [
        {
            "service": image["service"],
            "repository": image["repository"],
            "tag": image["tag"],
            "archive": image["archive"],
            "required": True,
        }
        for image in build_result["images"]
        if image["built"]
    ]

    release_answers = _copy_resources_and_rewrite_answers(path, release_dir, answers)
    _write_compose_file(path, release_dir, inspection_result["docker"], build_result)

    manifest = build_release_manifest(
        application=application,
        version=version,
        summary=summary or f"{application['name']} {version}",
        project_path=str(path),
        git_facts=inspection_result["git"],
        answers=release_answers,
        docker_images=docker_images,
    )
    manifest_path = _write_manifest_atomically(release_dir, manifest)

    return {
        "release_directory": str(release_dir),
        "manifest_path": str(manifest_path),
        "application": application,
        "version": version,
        "images": docker_images,
    }
