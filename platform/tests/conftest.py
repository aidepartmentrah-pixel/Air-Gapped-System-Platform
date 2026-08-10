"""Session-scoped fixture that starts a real, disposable PostgreSQL
container for the tests that need a real database (Registry Connectivity,
Migration) — same "real container, not mocked" standard the Packager used
for its own required tests.
"""

from __future__ import annotations

import subprocess
import time

import pytest
from sqlalchemy import create_engine, text

_IMAGE = "postgres:16"
_CONTAINER_NAME = "rah-platform-pl0-test-postgres"
_HOST_PORT = 55432
_DB_URL = f"postgresql+psycopg://rah_platform:rah_platform@localhost:{_HOST_PORT}/rah_platform"


@pytest.fixture(scope="session")
def postgres_url():
    subprocess.run(["docker", "rm", "-f", _CONTAINER_NAME], capture_output=True, check=False)
    subprocess.run(
        [
            "docker", "run", "-d", "--name", _CONTAINER_NAME,
            "-p", f"{_HOST_PORT}:5432",
            "-e", "POSTGRES_DB=rah_platform",
            "-e", "POSTGRES_USER=rah_platform",
            "-e", "POSTGRES_PASSWORD=rah_platform",
            _IMAGE,
        ],
        check=True,
        capture_output=True,
    )

    engine = create_engine(_DB_URL)
    deadline = time.monotonic() + 30
    last_error = None
    while time.monotonic() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1)
    else:
        subprocess.run(["docker", "rm", "-f", _CONTAINER_NAME], capture_output=True, check=False)
        raise RuntimeError(f"Test PostgreSQL container never became ready: {last_error}")
    engine.dispose()

    yield _DB_URL

    subprocess.run(["docker", "rm", "-f", _CONTAINER_NAME], capture_output=True, check=False)
