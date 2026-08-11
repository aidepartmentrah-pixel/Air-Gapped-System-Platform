"""Deployment Planning and Configuration — PL5.

`deployment_configuration` is what `prepare_update`'s "preserve existing
configuration" (§7.15 Configuration Preservation Rule) reads from. No
real installation exists until `PL6`, so nothing writes this table for
real yet — `PL5`'s own tests seed it directly, same pattern as `PL4`
seeding `deployments`.

Secret values are never stored in plaintext: `value` stays null for
`secret=true` rows; `secret_reference` holds a stand-in reference only
(§7.16 Secret-State Rule).

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_configuration",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "deployment_id", UUID(as_uuid=False), sa.ForeignKey("deployments.deployment_id"), nullable=False
        ),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("value", sa.String, nullable=True),
        sa.Column("secret", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("secret_reference", sa.String, nullable=True),
        sa.Column("source", sa.String, nullable=False),
        sa.UniqueConstraint("deployment_id", "key", name="uq_deployment_configuration_deployment_key"),
    )


def downgrade() -> None:
    op.drop_table("deployment_configuration")
