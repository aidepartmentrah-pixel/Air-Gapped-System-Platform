"""PostgreSQL connectivity — the Platform Operational Registry connection.

PL0 only needs to prove the connection works and that migrations can run;
no application tables exist yet (see `migrations/versions/0001_initial.py`).
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from rah_platform.errors import DatabaseConnectionError


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def check_connectivity(database_url: str) -> dict:
    engine = make_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise DatabaseConnectionError(
            "Could not connect to the Platform Operational Registry.",
            stage="READINESS",
            details={"reason": str(exc)},
        ) from exc
    finally:
        engine.dispose()
    return {"reachable": True}
