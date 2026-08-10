# RAH Offline Installation Platform backend runtime — PL0.
#
# Runs Docker-outside-of-Docker, same as the Packager (see
# packager/Dockerfile): this image does not run a Docker daemon itself.
# At `docker run`/Compose time, the host's Docker socket must be bind
# mounted in (-v /var/run/docker.sock:/var/run/docker.sock) for the
# readiness check (and later slices' Docker/Compose work) to reach the
# host Engine.

FROM python:3.11-slim

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
