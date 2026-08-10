"""Real Docker builds against the real host Engine — no mocks. Consistent
with this project's "prefer real proofs" discipline (see
docs/development/1. Development Strategy and Engineering Rules.md) and
with the established "the Packager needs internet/Docker, the Platform
doesn't" split: these tests require a running Docker Engine, same as
`rah health`'s connectivity check already did.

Every test that builds a real image cleans its own tag up afterward via
`_remove_image`, so repeated runs don't accumulate stale images in the
developer's local Docker.
"""

from pathlib import Path

import docker
import pytest

from rah_packager.docker_build import build_release_images
from rah_packager.errors import DockerBuildFailedError, MalformedComposeError

FIXTURES = Path(__file__).parent / "fixtures" / "projects"
SLUG = "pytest-p5"


def _remove_image(client, repository: str, tag: str) -> None:
    try:
        client.images.remove(f"{repository}:{tag}", force=True)
    except docker.errors.ImageNotFound:
        pass


# --- Trivial one-container application ---


def test_trivial_one_container_builds_and_exports(tmp_path):
    client = docker.from_env()
    output_dir = tmp_path / "workspace"

    try:
        result = build_release_images(
            FIXTURES / "trivial-one-container", SLUG, "0.0.1", output_dir
        )

        assert result["images"] == [
            {
                "service": "app",
                "built": True,
                "image": f"rah-{SLUG}-app:0.0.1",
                "repository": f"rah-{SLUG}-app",
                "tag": "0.0.1",
                "image_id": result["images"][0]["image_id"],
                "size_bytes": result["images"][0]["size_bytes"],
                "archive": "docker-images/rah-pytest-p5-app_0.0.1.tar",
                "build_log": result["images"][0]["build_log"],
            }
        ]
        assert result["images"][0]["size_bytes"] > 0
        assert result["images"][0]["build_log"]  # real build log lines captured

        archive_path = output_dir / "docker-images" / "rah-pytest-p5-app_0.0.1.tar"
        assert archive_path.is_file()
        assert archive_path.stat().st_size > 0

        # Exported image can be loaded again — proves the archive is a
        # genuinely valid, self-contained Docker image, not just bytes.
        _remove_image(client, f"rah-{SLUG}-app", "0.0.1")
        with open(archive_path, "rb") as archive_file:
            loaded = client.images.load(archive_file.read())
        assert len(loaded) == 1
        assert loaded[0].id == result["images"][0]["image_id"]
    finally:
        _remove_image(client, f"rah-{SLUG}-app", "0.0.1")


# --- Simple frontend/backend application (multi-service) ---


def test_simple_frontend_backend_builds_expected_images(tmp_path):
    client = docker.from_env()
    output_dir = tmp_path / "workspace"

    try:
        result = build_release_images(
            FIXTURES / "compose-multi-service", SLUG, "0.0.1", output_dir
        )

        by_service = {entry["service"]: entry for entry in result["images"]}
        assert set(by_service) == {"backend", "frontend", "database"}

        for name in ("backend", "frontend"):
            entry = by_service[name]
            assert entry["built"] is True
            assert entry["repository"] == f"rah-{SLUG}-{name}"
            assert entry["image"] == f"rah-{SLUG}-{name}:0.0.1"
            archive_path = output_dir / entry["archive"]
            assert archive_path.is_file()
            assert archive_path.stat().st_size > 0

        # A service with only a prebuilt `image:` reference (no `build:`
        # key) is reported, not built or exported — out of P5's scope.
        assert by_service["database"] == {
            "service": "database",
            "built": False,
            "image": "postgres:16",
            "repository": None,
            "tag": None,
            "archive": None,
            "build_log": None,
        }
    finally:
        _remove_image(client, f"rah-{SLUG}-backend", "0.0.1")
        _remove_image(client, f"rah-{SLUG}-frontend", "0.0.1")


# --- Deliberately broken Dockerfile ---


def test_broken_dockerfile_raises_structured_error(tmp_path):
    with pytest.raises(DockerBuildFailedError) as exc_info:
        build_release_images(FIXTURES / "broken-dockerfile", SLUG, "0.0.1", tmp_path / "workspace")

    assert exc_info.value.code == "PKG-DOCKER-BUILD-FAILED"
    assert exc_info.value.service == "app"
    assert not (tmp_path / "workspace" / "docker-images").exists()


# --- Malformed Compose rejected before any Docker interaction ---


def test_malformed_compose_rejected_before_build(tmp_path):
    with pytest.raises(MalformedComposeError) as exc_info:
        build_release_images(FIXTURES / "malformed-compose", SLUG, "0.0.1", tmp_path / "workspace")

    assert exc_info.value.code == "PKG-DOCKER-MALFORMED-COMPOSE"
    assert not (tmp_path / "workspace").exists()


# --- Fail-fast: a partial build workspace survives a later failure ---


def test_partial_build_workspace_survives_a_later_failure(tmp_path):
    """One working service, one broken — proves the first service's real,
    already-exported archive is left on disk (a real partial workspace),
    while the whole operation still raises and never becomes a
    "finished"-looking result.
    """
    project = tmp_path / "project"
    (project / "good").mkdir(parents=True)
    # `FROM scratch` alone with no further instruction produces no image ID
    # at all ("No image was generated") — a real quirk of the trivial fixture,
    # not something worth reusing here. LABEL is enough to get a real layer.
    (project / "good" / "Dockerfile").write_text("FROM scratch\nLABEL test=true\n")
    (project / "bad").mkdir(parents=True)
    (project / "bad" / "Dockerfile").write_text("FROM scratch\nNOTAREALINSTRUCTION x\n")
    (project / "docker-compose.yml").write_text(
        "services:\n"
        "  good:\n"
        "    build:\n      context: ./good\n      dockerfile: Dockerfile\n"
        "  bad:\n"
        "    build:\n      context: ./bad\n      dockerfile: Dockerfile\n"
    )

    client = docker.from_env()
    output_dir = tmp_path / "workspace"
    try:
        with pytest.raises(DockerBuildFailedError) as exc_info:
            build_release_images(project, SLUG, "0.0.1", output_dir)
        assert exc_info.value.service == "bad"

        # "good" was built and exported before "bad" failed — a real,
        # partial workspace, not cleaned up, but never a finalized Release
        # (this module has no concept of one).
        assert (output_dir / "docker-images" / f"rah-{SLUG}-good_0.0.1.tar").is_file()
        assert not (output_dir / "docker-images" / f"rah-{SLUG}-bad_0.0.1.tar").exists()
    finally:
        _remove_image(client, f"rah-{SLUG}-good", "0.0.1")
