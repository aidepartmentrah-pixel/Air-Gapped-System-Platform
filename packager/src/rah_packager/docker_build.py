"""`rah build` — P5 Docker Build and Artifact Preparation.

"Implement internal capabilities" (the P5 spec's own framing) rather than
a full pipeline command: this module is deliberately project-identity-
agnostic — `application_slug` and `version` are caller-supplied, not
derived from Project Version State — so it stays testable in isolation
against bare fixture directories, the same way P2's inspection modules
are. Nothing here reads or writes `.rah/project-state.json`; `rah build`
does not require `rah init` to have run first, and there is deliberately
no "project not initialized" gate in this slice (unlike P4).

Scope, checked against the P5 spec's own wording ("Docker image build",
not "docker pull"): only Compose services that declare their own
`build:` context are built and exported. A service that only references
a prebuilt `image:` (e.g. a base database image) is reported in the
inventory but not built, tagged, or exported here — the Packager didn't
produce that image, so building/exporting it is out of this slice's
scope (possibly P6's job, possibly out of scope entirely; not decided
here).

Compose validation is not reimplemented — `inspect_docker()` (P2) already
raises `MalformedComposeError` for a structurally broken Compose file,
and that's exactly the gate this module needs too.

Fails fast: the first failing service build raises immediately, and
whatever was already built/exported before that point is left on disk in
`output_dir` — a real, partial build workspace. It is never treated as a
finalized Release; only P6 (Release Construction, not yet built) knows
what a finalized Release looks like.

Naming convention (`rah-{application_slug}-{service}`, tag = the target
version, archive = `docker-images/{repository}_{tag}.tar`) matches the
one concrete example in the architecture's `docker` manifest section
verbatim (`docs/architecture/4. Stage 4 — Choose Implementation
Mechanisms.md` §18) — not invented in parallel.
"""

from __future__ import annotations

import os
from pathlib import Path

import docker
from docker.errors import DockerException

from rah_packager.docker_inspection import inspect_docker
from rah_packager.errors import DockerBuildFailedError, DockerImageExportError

_BUILD_LOG_TAIL_LINES = 20


def _repository_name(application_slug: str, service_name: str) -> str:
    return f"rah-{application_slug}-{service_name}"


def _archive_filename(repository: str, tag: str) -> str:
    return f"{repository}_{tag}.tar"


def _extract_log_lines(build_log_stream) -> list[str]:
    return [
        entry["stream"].rstrip("\n")
        for entry in build_log_stream
        if isinstance(entry, dict) and entry.get("stream")
    ]


def _build_one_image(client, repo_path: Path, service: dict, repository: str, tag: str):
    build_info = service["build"]
    context_path = repo_path / build_info["context"]
    dockerfile = build_info["dockerfile"] or "Dockerfile"

    try:
        image, build_log_stream = client.images.build(
            path=str(context_path),
            dockerfile=dockerfile,
            tag=f"{repository}:{tag}",
            rm=True,
        )
    except docker.errors.BuildError as exc:
        log_lines = _extract_log_lines(exc.build_log)
        raise DockerBuildFailedError(
            service["name"], exc.msg, log_lines[-_BUILD_LOG_TAIL_LINES:]
        ) from exc
    except DockerException as exc:
        raise DockerBuildFailedError(service["name"], str(exc), []) from exc

    return image, _extract_log_lines(build_log_stream)


def _export_one_image(image, service_name: str, archive_path: Path) -> None:
    try:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with open(archive_path, "wb") as archive_file:
            for chunk in image.save():
                archive_file.write(chunk)
    except OSError as exc:
        raise DockerImageExportError(service_name, str(exc)) from exc


def build_release_images(
    project_path: str | os.PathLike,
    application_slug: str,
    version: str,
    output_dir: str | os.PathLike,
) -> dict:
    repo_path = Path(project_path)
    output_path = Path(output_dir)

    inspection = inspect_docker(repo_path)  # raises MalformedComposeError if broken
    client = docker.from_env()

    images = []
    for service in inspection["services"]:
        if service["build"] is None:
            images.append(
                {
                    "service": service["name"],
                    "built": False,
                    "image": service["image"],
                    "repository": None,
                    "tag": None,
                    "archive": None,
                    "build_log": None,
                }
            )
            continue

        repository = _repository_name(application_slug, service["name"])
        image, build_log = _build_one_image(client, repo_path, service, repository, version)

        archive_filename = _archive_filename(repository, version)
        archive_relative = (Path("docker-images") / archive_filename).as_posix()
        _export_one_image(image, service["name"], output_path / "docker-images" / archive_filename)

        images.append(
            {
                "service": service["name"],
                "built": True,
                "image": f"{repository}:{version}",
                "repository": repository,
                "tag": version,
                "image_id": image.id,
                "size_bytes": image.attrs.get("Size"),
                "archive": archive_relative,
                "build_log": build_log,
            }
        )

    return {"output_directory": str(output_path), "images": images}
