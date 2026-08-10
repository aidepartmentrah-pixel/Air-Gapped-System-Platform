import pytest

from rah_platform import db
from rah_platform.errors import DatabaseConnectionError


# --- Registry Connectivity Test (real PostgreSQL container, no mocking) ---


def test_connects_to_real_postgres(postgres_url):
    result = db.check_connectivity(postgres_url)
    assert result == {"reachable": True}


# --- PostgreSQL Failure Test ---


def test_connection_failure_raises_structured_error():
    bad_url = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/does_not_exist"
    with pytest.raises(DatabaseConnectionError) as exc_info:
        db.check_connectivity(bad_url)
    assert exc_info.value.code == "PLT-DATABASE-003"
