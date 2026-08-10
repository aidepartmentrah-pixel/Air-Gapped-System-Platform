"""Initial schema — PL0 baseline.

PL0 does not yet manage Applications (see the PL0 Objective), so this
migration does not create `applications`/`releases`/`operations` — those
belong to the slices that introduce them (`operations` in PL1, per the
proposal; `applications`/`releases` in PL3). This migration only proves
the migration mechanism itself works end to end against a real, empty
PostgreSQL database, via one real table.

Revision ID: 0001
Revises:
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_schema_info",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("baseline", sa.String, nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("INSERT INTO platform_schema_info (baseline) VALUES ('PL0')")


def downgrade() -> None:
    op.drop_table("platform_schema_info")
