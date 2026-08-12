"""Backup and Update — PL8a.

`backups` — every backup's own storage location, checksum, and
artifact-lifecycle status, kept independent of `operations.status`
(architecture "Choose Implementation Mechanisms" doc §13.1: "The
database does not necessarily contain backup data. It records where
backup data exists and what happened.").

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backups",
        sa.Column("backup_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("operation_id", UUID(as_uuid=False), sa.ForeignKey("operations.operation_id"), nullable=False),
        sa.Column(
            "application_id", UUID(as_uuid=False), sa.ForeignKey("applications.application_id"), nullable=False
        ),
        sa.Column(
            "deployment_id", UUID(as_uuid=False), sa.ForeignKey("deployments.deployment_id"), nullable=True
        ),
        sa.Column("backup_type", sa.String, nullable=False),
        sa.Column("storage_path", sa.String, nullable=False),
        sa.Column("checksum", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("backups")
