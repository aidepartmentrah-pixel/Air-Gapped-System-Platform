# RAH Offline Installation Platform backend runtime — PL0.
#
# Runs Docker-outside-of-Docker, same as the Packager (see
# packager/Dockerfile): this image does not run a Docker daemon itself.
# At `docker run`/Compose time, the host's Docker socket must be bind
# mounted in (-v /var/run/docker.sock:/var/run/docker.sock) for the
# readiness check (and later slices' Docker/Compose work) to reach the
# host Engine.
#
# PL6 adds the real `docker`/`docker compose` CLI (client only — talks to
# the host's daemon over the bind-mounted socket, same as the Packager's
# own docker-py usage, just needed here as real shell commands since
# Manifest-declared lifecycle scripts invoke them directly per §12.6 —
# the Platform doesn't reimplement installation commands, it only invokes
# the Release's own declared entry point, which needs a real `docker`
# binary on PATH to do its real work.

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install --no-install-recommends -y docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
COPY alembic.ini ./
COPY migrations/ ./migrations/

RUN pip install --no-cache-dir .

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "rah_platform.app:app", "--host", "0.0.0.0", "--port", "8000"]
