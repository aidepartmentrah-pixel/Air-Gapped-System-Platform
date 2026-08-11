"""Registry table definitions — PL1 introduces `operations`,
`operation_events`, and `operation_logs`. No `applications`/`releases`
tables exist yet (PL3's job), so `operations.application_id` is a plain
UUID column without a foreign key for now — the constraint gets added
once `applications` exists.

Plain SQLAlchemy Core `Table` objects, not the ORM — PL1's access
patterns are simple enough (a handful of inserts/selects per operation)
that a declarative layer would add ceremony without buying anything yet.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = sa.MetaData()

operations = sa.Table(
    "operations",
    metadata,
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

operation_events = sa.Table(
    "operation_events",
    metadata,
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

operation_logs = sa.Table(
    "operation_logs",
    metadata,
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
