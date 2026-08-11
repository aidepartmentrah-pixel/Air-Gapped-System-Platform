"""Release Discovery — PL2.

`release_candidates` is bookkeeping about what `scan_releases` has
physically found in Release Storage, keyed by `directory_name` so a
repeat scan of the same physical directory updates the existing row
(via upsert) rather than creating an uncontrolled duplicate (§3.4
Release Scan Workflow, step 7: "Compare with known Release Storage
records").

Not a registration of an Application or Release — that distinction is
architectural (§7.5 Discovery, Import, and Deployment Separation), which
is why this table has no relationship to `operations` and `scan_releases`
never touches the Operation Framework: scanning is explicitly read-only
and reversible, unlike import/install/update/backup/restore/recovery
(§7.12 Operation Attempt Rule).

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_candidates",
        sa.Column("candidate_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("directory_name", sa.String, nullable=False, unique=True),
        sa.Column("application_slug", sa.String, nullable=True),
        sa.Column("release_version", sa.String, nullable=True),
        sa.Column("discovery_state", sa.String, nullable=False),
        sa.Column("already_imported", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("issues", JSONB, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("release_candidates")
