"""Host Docker Engine connectivity.

The Packager runs Docker-outside-of-Docker: it is itself expected to run
inside a container (see Dockerfile), with the host's Docker socket bind
mounted in, and talks to the *host's* Docker Engine through that socket —
never a Docker-in-Docker daemon of its own.
"""

from __future__ import annotations

import docker
from docker.errors import DockerException

from rah_packager.errors import DockerUnavailableError


def check_connectivity() -> dict:
    """Ping the host Docker Engine and return basic identifying facts.

    Raises DockerUnavailableError (a PackagerError) rather than letting
    the underlying docker-py exception escape — P0's Failure Test requires
    a deterministic Packager error, not a crash, when Docker is
    unreachable.
    """
    try:
        client = docker.from_env()
        client.ping()
        info = client.info()
    except DockerException as exc:
        raise DockerUnavailableError(str(exc)) from exc

    return {
        "reachable": True,
        "server_version": info.get("ServerVersion"),
        "operating_system": info.get("OperatingSystem"),
        "architecture": info.get("Architecture"),
    }
