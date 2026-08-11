"""Session-scoped fixture that starts a real, disposable PostgreSQL
container for the tests that need a real database (Registry Connectivity,
Migration) — same "real container, not mocked" standard the Packager used
for its own required tests.
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from rah_platform.models import applications

PLATFORM_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PLATFORM_ROOT.parent
CONTRACTS_PATH = REPO_ROOT / "contracts" / "1.0"
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "releases"

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


@pytest.fixture(scope="session")
def migrated_db_url(postgres_url):
    """`postgres_url` migrated once (head — all revisions), shared by every
    test that needs real `operations`/`operation_events`/`operation_logs`
    tables rather than just a raw connection.
    """
    env = {**os.environ, "RAH_DATABASE_URL": postgres_url}
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=PLATFORM_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return postgres_url


@pytest.fixture()
def db_engine(migrated_db_url):
    """A real engine against the migrated test database, truncated after
    each test so operation-lock and identity tests always start from a
    clean slate. Deletion order respects foreign keys: children first.
    """
    engine = create_engine(migrated_db_url)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM release_candidates"))
        conn.execute(text("DELETE FROM operation_logs"))
        conn.execute(text("DELETE FROM operation_events"))
        conn.execute(text("DELETE FROM operations"))
        conn.execute(text("DELETE FROM release_storage"))
        conn.execute(text("DELETE FROM releases"))
        conn.execute(text("DELETE FROM applications"))
    engine.dispose()


def seed_application(engine, *, slug: str | None = None, name: str | None = None) -> str:
    """Inserts a real `applications` row and returns its id. Needed by
    every operation test since PL3 added the foreign key from
    `operations.application_id` — PL1's "synthetic test operation" still
    needs a real application to reference, it just doesn't need a real
    Release.
    """
    application_id = str(uuid.uuid4())
    slug = slug or f"test-app-{application_id[:8]}"
    with engine.begin() as conn:
        conn.execute(
            applications.insert().values(
                application_id=application_id,
                slug=slug,
                name=name or slug,
                description=None,
                created_at=datetime.now(timezone.utc),
            )
        )
    return application_id
