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

from rah_platform.models import applications, deployment_configuration, deployments, release_storage, releases

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
        # verification_runs FKs operations/releases/applications;
        # verification_checks FKs verification_runs; reconciliations FKs
        # applications — all must go before those tables are cleared.
        conn.execute(text("DELETE FROM verification_checks"))
        conn.execute(text("DELETE FROM verification_runs"))
        conn.execute(text("DELETE FROM reconciliations"))
        # backups FKs operations/applications/deployments — same ordering
        # requirement as verification_runs above.
        conn.execute(text("DELETE FROM backups"))
        # applications.active_deployment_id <-> deployments.application_id
        # is a real circular FK — break it before deleting either side.
        conn.execute(text("UPDATE applications SET active_deployment_id = NULL"))
        conn.execute(text("DELETE FROM deployment_configuration"))
        conn.execute(text("DELETE FROM deployments"))
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


def seed_active_deployment(engine, *, application_id: str, release_id: str, verification_status: str = "PASS") -> str:
    """Inserts a `deployments` row and sets it as the application's
    `active_deployment_id`. No real install exists until `PL6` — `PL4`'s
    own tests seed this directly to exercise the already-installed
    decision paths, exactly as the pre-PL0 review anticipated for this
    slice.
    """
    deployment_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            deployments.insert().values(
                deployment_id=deployment_id,
                application_id=application_id,
                release_id=release_id,
                operation_id=None,
                verification_status=verification_status,
                deployed_at=datetime.now(timezone.utc),
            )
        )
        conn.execute(
            applications.update()
            .where(applications.c.application_id == application_id)
            .values(active_deployment_id=deployment_id)
        )
    return deployment_id


def seed_deployment_configuration(
    engine, *, deployment_id: str, key: str, value: str | None = None, secret: bool = False, source: str = "operator"
) -> None:
    """Inserts a `deployment_configuration` row directly — `PL5`'s own
    tests seed this to exercise `prepare_update`'s "preserve existing
    configuration" path, since nothing writes this table for real until
    `PL6` performs a real installation.
    """
    with engine.begin() as conn:
        conn.execute(
            deployment_configuration.insert().values(
                deployment_id=deployment_id,
                key=key,
                value=None if secret else value,
                secret=secret,
                secret_reference=f"secret-ref:{key}" if secret else None,
                source=source,
            )
        )


def seed_release(
    engine,
    *,
    application_id: str,
    version: str,
    supported_operations: dict | None = None,
    accepted_installed_versions: list[str] | None = None,
    storage_state: str = "AVAILABLE",
    configuration_inputs: list[dict] | None = None,
    docker_images: list[dict] | None = None,
    database: dict | None = None,
    verification_checks: list[str] | None = None,
) -> str:
    """Inserts a `releases` (+ `release_storage`) row directly, with a
    hand-built manifest, bypassing `release_import.import_release`
    entirely. `PL4`'s decision logic only cares about Registry state, not
    how a Release got there — this lets each test exercise an exact
    `supported_operations`/`transition` combination without needing a
    dedicated Golden Fixture directory per scenario. `PL5` extends this
    with `configuration_inputs`/`docker_images`/`database`/
    `verification_checks` for the same reason — planning logic needs
    precise, varied declarations that a single Golden Fixture can't all
    provide at once.
    """
    release_id = str(uuid.uuid4())
    manifest = {
        "manifest_schema_version": "1.0",
        "application": {"name": "Seeded App", "slug": "seeded-app", "description": "test"},
        "release": {
            "version": version,
            "created_at": "2026-08-01T00:00:00+00:00",
            "summary": f"Seeded release {version}",
            "release_type": "application",
            "engineering_state": "awaiting_offline_qualification",
        },
        "compatibility": {"release_contract_version": "1.0", "minimum_rah_oip_version": "1.0.0", "supported_architectures": ["amd64"]},
        "deployment": {
            "canonical_path": "/opt/rah/apps/seeded-app",
            "compose_project_name": "rah-seeded-app",
            "entrypoints": {},
            "supported_operations": supported_operations or {"fresh_install": True},
            "transition": {"accepted_installed_versions": accepted_installed_versions} if accepted_installed_versions else {},
        },
        "configuration": {
            "template": "configuration/app.env.template",
            "inputs": configuration_inputs if configuration_inputs is not None else [],
        },
        "docker": {
            "compose_file": "compose/docker-compose.yml",
            "images": docker_images if docker_images is not None else [{"service": "backend", "repository": "seeded-app-backend", "tag": version, "archive": "docker-images/backend.tar", "required": True}],
        },
        "database": database if database is not None else {"required": False},
        "verification": {
            "entrypoint": "verify_deployment.sh",
            "required_checks": verification_checks if verification_checks is not None else ["docker_services"],
        },
    }
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            releases.insert().values(
                release_id=release_id,
                application_id=application_id,
                version=version,
                contract_version="1.0",
                manifest_schema_version="1.0",
                fingerprint=f"sha256:test-{release_id}",
                summary=manifest["release"]["summary"],
                manifest=manifest,
                created_at_engineering=manifest["release"]["created_at"],
                imported_at=now,
            )
        )
        conn.execute(
            release_storage.insert().values(
                release_id=release_id,
                directory_name=f"seeded-{version}",
                path=f"/data/releases/seeded-{version}",
                state=storage_state,
                integrity_verified=True,
                created_at=now,
                updated_at=now,
            )
        )
    return release_id


def wait_for_terminal_operation(engine, operation_id: str, *, timeout: float = 30.0):
    """Polls a real operation until it reaches a terminal state — the
    same thing a real UI/Jenkins client does against the async
    long-running-operation model (§5.3), used here because `PL6`'s
    install execution genuinely runs in a background thread.
    """
    from rah_platform import operations

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = operations.get_operation(engine, operation_id)
        if result["status"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return result
        time.sleep(0.2)
    raise TimeoutError(f"Operation {operation_id} did not reach a terminal state within {timeout}s")
