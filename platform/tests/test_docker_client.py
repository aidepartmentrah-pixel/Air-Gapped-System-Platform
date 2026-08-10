import pytest

from rah_platform import docker_client
from rah_platform.errors import DockerUnavailableError


# --- Docker Connectivity Test (real Docker Engine via bind-mounted socket, no mocking) ---


def test_reaches_real_docker_engine():
    result = docker_client.check_connectivity()
    assert result["reachable"] is True
    assert result["server_version"]


# --- Docker Failure Test ---


def test_docker_unavailable_raises_structured_error(monkeypatch):
    def fail_from_env():
        from docker.errors import DockerException

        raise DockerException("no such host")

    monkeypatch.setattr("rah_platform.docker_client.docker.from_env", fail_from_env)

    with pytest.raises(DockerUnavailableError) as exc_info:
        docker_client.check_connectivity()
    assert exc_info.value.code == "PLT-DOCKER-001"
