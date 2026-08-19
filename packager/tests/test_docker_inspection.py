from pathlib import Path

import pytest

from rah_packager.docker_inspection import inspect_docker
from rah_packager.errors import MalformedComposeError

FIXTURES = Path(__file__).parent / "fixtures" / "projects"


# --- Compose services parsed correctly / Dockerfiles mapped correctly ---


def test_multi_service_compose_parsed_correctly():
    result = inspect_docker(FIXTURES / "compose-multi-service")

    assert result["compose_file"] == "docker-compose.yml"
    assert sorted(result["dockerfiles"]) == [
        "backend/Dockerfile",
        "frontend/Dockerfile",
    ]

    services = {s["name"]: s for s in result["services"]}
    assert set(services) == {"backend", "frontend", "database"}

    assert services["backend"]["image"] is None
    assert services["backend"]["build"] == {"context": "./backend", "dockerfile": "Dockerfile"}

    # shorthand `build: ./frontend` (a plain string, not a mapping)
    assert services["frontend"]["build"] == {"context": "./frontend", "dockerfile": None}

    assert services["database"]["image"] == "alpine:3.19"
    assert services["database"]["build"] is None


# --- Missing optional resource reported as missing, not crash ---


def test_no_compose_or_dockerfile_reports_missing_not_crash(tmp_path):
    (tmp_path / "some_file.txt").write_text("nothing docker-related here")

    result = inspect_docker(tmp_path)

    assert result == {"dockerfiles": [], "compose_file": None, "services": []}


def test_compose_referencing_missing_dockerfile_does_not_crash():
    result = inspect_docker(FIXTURES / "missing-dockerfile")

    assert result["compose_file"] == "docker-compose.yml"
    assert result["dockerfiles"] == []  # build context exists, but no Dockerfile in it
    assert result["services"][0]["build"] == {"context": "./backend", "dockerfile": "Dockerfile"}


# --- Malformed Compose produces stable error ---


def test_malformed_compose_raises_structured_error():
    with pytest.raises(MalformedComposeError) as exc_info:
        inspect_docker(FIXTURES / "malformed-compose")

    assert exc_info.value.code == "PKG-DOCKER-MALFORMED-COMPOSE"


def test_compose_with_non_mapping_top_level_is_malformed(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("- just\n- a\n- list\n")

    with pytest.raises(MalformedComposeError):
        inspect_docker(tmp_path)


def test_compose_with_non_mapping_services_is_malformed(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: not-a-mapping\n")

    with pytest.raises(MalformedComposeError):
        inspect_docker(tmp_path)


# --- Dockerfile search ignores noise directories ---


def test_dockerfile_search_skips_node_modules(tmp_path):
    (tmp_path / "node_modules" / "some_dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "some_dep" / "Dockerfile").write_text("FROM scratch")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11-slim")

    result = inspect_docker(tmp_path)

    assert result["dockerfiles"] == ["Dockerfile"]
