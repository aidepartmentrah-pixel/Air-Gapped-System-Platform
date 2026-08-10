# RAH Packaging Engine runtime — P0.
#
# Runs Docker-outside-of-Docker: this image does not run a Docker daemon
# itself. At `docker run` time, the host's Docker socket must be bind
# mounted in (e.g. -v /var/run/docker.sock:/var/run/docker.sock on Linux,
# or the Docker Desktop equivalent on Windows) for `rah health` and later
# slices' Docker build/export work to reach the host Engine.

FROM python:3.11-slim

# git is a real runtime dependency from P2 (Repository Inspection) onward —
# the Packager shells out to it to read branch/commit/tag/dirty-state from
# the mounted repository. Not needed by P0/P1, which only ever check for
# `.git`'s existence.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

ENTRYPOINT ["rah"]
CMD ["--help"]
