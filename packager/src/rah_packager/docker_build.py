"""`rah build` — P5 Docker Build and Artifact Preparation.

"Implement internal capabilities" (the P5 spec's own framing) rather than
a full pipeline command: this module is deliberately project-identity-
agnostic — `application_slug` and `version` are caller-supplied, not
derived from Project Version State — so it stays testable in isolation
against bare fixture directories, the same way P2's inspection modules
are. Nothing here reads or writes `.rah/project-state.json`; `rah build`
does not require `rah init` to have run first, and there is deliberately
no "project not initialized" gate in this slice (unlike P4).

Scope: Compose services that declare their own `build:` context are
built and exported. A service that only references a prebuilt `image:`
(e.g. a base database image, `nginx`, `pgadmin`) is *pulled* and
exported instead — the Packager didn't produce that image, but
RC-OFF-002 ("every Compose service's image has a local offline archive")
doesn't care who produced it, only that a local archive exists. Pulled
images are never retagged: the archive is captured under the image's own
original reference, and the Compose file is left untouched for these
services (unlike built services, which get their `build:` stanza
rewritten to the new `image:` tag in construct_release.py — a pulled
image's `image:` reference was already correct).

One more case, found against a real app (HCopilot): a service with no
`build:` key isn't always an *external* prebuilt image — it can instead
be reusing another service's build output (e.g. a one-shot `db-init`
service declaring the same `image:` tag the app's own `backend` service
builds, so both run from one image without building it twice). Pulling
that tag fails outright (it was never published anywhere; it only ever
exists locally, once `backend` builds it) and even if a same-named public
image existed, it'd be the wrong one. Detected by cross-referencing every
build-less service's `image:` against every build-having service's own
declared `image:` tag *before* deciding to pull anything — a match means
"shares that service's build", not "pull me". These entries carry
`shares_build_of` instead of `built`/an archive of their own;
`construct_release.py`'s compose rewrite resolves their `image:` to
whatever tag the sibling actually got, the same way it already resolves
built services' tags.

Known limitation, not hit by any real acceptance app today: a service
declaring a bare, tagless image reference (e.g. `image: nginx`, implying
`:latest`) will be pulled and exported correctly, but RC-OFF-002's own
comparison (`repository:tag` reconstructed from the manifest vs. the
literal Compose string) won't match `"nginx"` against `"nginx:latest"`.
Every real image reference seen so far carries an explicit tag.

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
from rah_packager.errors import DockerBuildFailedError, DockerImageExportError, DockerPullFailedError

_BUILD_LOG_TAIL_LINES = 20


def _repository_name(application_slug: str, service_name: str) -> str:
    return f"rah-{application_slug}-{service_name}"


def _archive_filename(repository: str, tag: str) -> str:
    return f"{repository}_{tag}.tar"


def _sanitize_archive_stem(image_ref: str) -> str:
    return image_ref.replace("/", "_").replace(":", "_")


def _split_repository_tag(image_ref: str) -> tuple[str, str]:
    # The tag is the part after the *last* colon, unless that part
    # contains a `/` — which means the colon was actually a registry
    # host's `:port` (e.g. `myregistry:5000/image`, no tag at all).
    repository, sep, tag = image_ref.rpartition(":")
    if not sep or "/" in tag:
        return image_ref, "latest"
    return repository, tag


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


def _pull_one_image(client, image_ref: str, service_name: str):
    try:
        return client.images.pull(image_ref)
    except DockerException as exc:
        raise DockerPullFailedError(service_name, image_ref, str(exc)) from exc


def _export_one_image(image, service_name: str, archive_path: Path, image_ref: str) -> None:
    # `named=` is load-bearing, not cosmetic: docker-py's own docs say
    # plainly that the default (`named=False`) "will not retain repository
    # and tag information for this image." Found live during the P7 Real
    # Manual Acceptance Test — every prior live-proof only ever re-loaded an
    # export back into the *same* Docker Desktop installation that built it,
    # which never surfaced this; a genuinely separate Docker Engine (the
    # offline VM) loaded the archive as a completely untagged image, so
    # `docker compose up` couldn't find it locally and fell back to a
    # registry pull instead — the exact failure mode offline install exists
    # to prevent. This also explains a previously-documented, only
    # partially-understood P7 finding: exported archives observed as
    # OCI-format with `RepoTags: null` — that was already evidence of this
    # bug, not a separate, merely cosmetic Docker-format quirk.
    #
    # `named=True` alone is not enough: it silently picks `image.tags[0]`,
    # and a content-addressed image ID accumulates every tag it was ever
    # built/pulled with in this Docker Engine's history (nothing untags the
    # previous version automatically) — found live immediately after the
    # fix above, when `tags[0]` resolved to a stale prior version's tag
    # instead of the one this Release actually declares. Passing the exact
    # `image_ref` this call already computed removes the ambiguity: it's
    # one of the image's real tags (this function is only ever called right
    # after that exact tag was just built or pulled), never a guess.
    try:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with open(archive_path, "wb") as archive_file:
            for chunk in image.save(named=image_ref):
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

    # Built-and-tagged services' own declared image: values, so a
    # build-less service referencing the same tag is recognized as
    # sharing that build rather than something to pull.
    built_image_tags = {
        service["image"]: service["name"]
        for service in inspection["services"]
        if service["build"] is not None and service["image"]
    }

    images = []
    for service in inspection["services"]:
        if service["build"] is None:
            image_ref = service["image"]

            shares_build_of = built_image_tags.get(image_ref)
            if shares_build_of is not None:
                images.append(
                    {
                        "service": service["name"],
                        "built": False,
                        "exported": False,
                        "shares_build_of": shares_build_of,
                        "image": None,
                        "repository": None,
                        "tag": None,
                        "archive": None,
                        "build_log": None,
                    }
                )
                continue

            repository, tag = _split_repository_tag(image_ref)
            image = _pull_one_image(client, image_ref, service["name"])

            archive_filename = _sanitize_archive_stem(image_ref) + ".tar"
            archive_relative = (Path("docker-images") / archive_filename).as_posix()
            _export_one_image(image, service["name"], output_path / "docker-images" / archive_filename, image_ref)

            images.append(
                {
                    "service": service["name"],
                    "built": False,
                    "exported": True,
                    "image": image_ref,
                    "repository": repository,
                    "tag": tag,
                    "image_id": image.id,
                    "size_bytes": image.attrs.get("Size"),
                    "archive": archive_relative,
                    "build_log": None,
                }
            )
            continue

        repository = _repository_name(application_slug, service["name"])
        image, build_log = _build_one_image(client, repo_path, service, repository, version)

        archive_filename = _archive_filename(repository, version)
        archive_relative = (Path("docker-images") / archive_filename).as_posix()
        _export_one_image(
            image, service["name"], output_path / "docker-images" / archive_filename, f"{repository}:{version}"
        )

        images.append(
            {
                "service": service["name"],
                "built": True,
                "exported": True,
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
