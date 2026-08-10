"""Docker Engine connectivity, via Docker-outside-of-Docker — the same
pattern already proven for the Packager (`packager/Dockerfile`,
`packager/src/rah_packager/docker_client.py`): the Platform backend does
not run its own Docker daemon, it reaches the host Engine through
`/var/run/docker.sock` bind-mounted in at `docker run`/Compose time.
"""

from __future__ import annotations

import docker
from docker.errors import DockerException

from rah_platform.errors import DockerUnavailableError


def check_connectivity() -> dict:
    try:
        client = docker.from_env()
        version = client.version()
    except DockerException as exc:
        raise DockerUnavailableError(
            "Could not reach the host Docker Engine.",
            stage="READINESS",
            details={"reason": str(exc)},
        ) from exc
    return {"reachable": True, "server_version": version.get("Version")}
