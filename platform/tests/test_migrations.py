import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, text

PLATFORM_ROOT = Path(__file__).resolve().parent.parent


# --- Migration Test: an empty database can be migrated to the expected initial schema ---


def test_empty_database_migrates_to_initial_schema(postgres_url):
    env = {**os.environ, "RAH_DATABASE_URL": postgres_url}
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=PLATFORM_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT baseline FROM platform_schema_info")).fetchone()
        assert row[0] == "PL0"

        version = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        assert version[0] == "0001"
    engine.dispose()
