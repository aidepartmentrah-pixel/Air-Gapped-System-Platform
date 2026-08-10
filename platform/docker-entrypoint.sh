#!/bin/sh
# Waits for PostgreSQL to accept connections, runs migrations, then execs
# the real command (normally uvicorn). The wait loop only covers Compose
# startup ordering (Postgres container still booting) — it is not what
# PL0's "PostgreSQL Failure" test exercises, which stops Postgres *after*
# the backend is already up and migrated.
set -e

echo "docker-entrypoint: waiting for PostgreSQL..."
attempt=0
until python -c "
import sys
from sqlalchemy import create_engine, text
import os
url = os.environ.get('RAH_DATABASE_URL', 'postgresql+psycopg://rah_platform:rah_platform@localhost:5432/rah_platform')
try:
    create_engine(url).connect().close()
except Exception as exc:
    sys.exit(1)
"; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "docker-entrypoint: PostgreSQL did not become available in time, continuing anyway"
        break
    fi
    sleep 2
done

echo "docker-entrypoint: running migrations..."
alembic upgrade head

echo "docker-entrypoint: starting: $*"
exec "$@"
