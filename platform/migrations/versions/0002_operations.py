"""Operation Framework tables — PL1.

`operations` + `operation_events` implement the canonical execution model
(architecture §3, §7.12 Operation Attempt Rule). `operation_logs` backs
`GET /operations/{id}/logs` (§2.8) separately from the structured event
timeline, matching the architecture's own split between "events" and
"logs" as two distinct endpoints/concepts.

The application-operation lock (§7.13, Architecture V1 Gap 1: locking
covers every `operation_type` via `operations.application_id` + a
non-terminal `status`) is enforced at the database level with a partial
unique index — at most one row per `application_id` may be in `PENDING`
or `RUNNING` at a time. This makes lock acquisition/release atomic and
race-free without any application-level locking logic: acquiring the
lock is just "the INSERT succeeded," and releasing it is just "the status
UPDATE moved the row out of PENDING/RUNNING."

`operations.application_id` has no foreign key yet — `applications`
doesn't exist until PL3. The constraint is added once that table exists.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations",
        sa.Column("operation_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("operation_type", sa.String, nullable=False),
        sa.Column("application_id", UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("stage", sa.String, nullable=True),
        sa.Column("requested_by", sa.String, nullable=False),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_operations_active_lock",
        "operations",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'RUNNING')"),
    )

    op.create_table(
        "operation_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "operation_id",
            UUID(as_uuid=False),
            sa.ForeignKey("operations.operation_id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("message", sa.String, nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("operation_id", "sequence", name="uq_operation_events_operation_sequence"),
    )

    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "operation_id",
            UUID(as_uuid=False),
            sa.ForeignKey("operations.operation_id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("level", sa.String, nullable=False),
        sa.Column("message", sa.String, nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("operation_id", "sequence", name="uq_operation_logs_operation_sequence"),
    )


def downgrade() -> None:
    op.drop_table("operation_logs")
    op.drop_table("operation_events")
    op.drop_index("ix_operations_active_lock", table_name="operations")
    op.drop_table("operations")
