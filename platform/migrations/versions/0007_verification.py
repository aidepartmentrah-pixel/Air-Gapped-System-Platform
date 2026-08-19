"""Verification and Host Reconciliation — PL7.

`verification_runs`/`verification_checks` — every verification run
preserved independently (§7.25 Verification History Rule: "A later
passing verification shall not erase an earlier failure"), each check
recorded separately per run (§5.15).

`reconciliations` — recorded drift findings (§7.27 Host Drift Rule:
"shall not silently modify historical state to make the mismatch
disappear").

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification_runs",
        sa.Column("verification_run_id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "application_id", UUID(as_uuid=False), sa.ForeignKey("applications.application_id"), nullable=False
        ),
        sa.Column(
            "expected_release_id", UUID(as_uuid=False), sa.ForeignKey("releases.release_id"), nullable=False
        ),
        sa.Column("operation_id", UUID(as_uuid=False), sa.ForeignKey("operations.operation_id"), nullable=False),
        sa.Column("verification_type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "verification_checks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "verification_run_id",
            UUID(as_uuid=False),
            sa.ForeignKey("verification_runs.verification_run_id"),
            nullable=False,
        ),
        sa.Column("check_key", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("message", sa.String, nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
    )

    op.create_table(
        "reconciliations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "application_id", UUID(as_uuid=False), sa.ForeignKey("applications.application_id"), nullable=False
        ),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("recorded_release", sa.String, nullable=True),
        sa.Column("observed_release", sa.String, nullable=True),
        sa.Column("drift_items", JSONB, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reconciliations")
    op.drop_table("verification_checks")
    op.drop_table("verification_runs")
