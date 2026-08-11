"""Application State and Action Intelligence — PL4.

`deployments` and `applications.active_deployment_id` — the schema
`get_active_deployment`/`get_available_actions` read from (§5.14's
`operation_id`/`deployment_id` distinction: `operation_id` identifies the
execution process, `deployment_id` identifies the detail record it
produced, linked via `deployments.operation_id`).

No real installation exists until `PL6` (Fresh Installation Execution),
so nothing writes `deployments` for real yet — `PL4` only needs to read
it, and its own tests seed it directly to exercise the already-installed
decision paths.

`applications` and `deployments` reference each other
(`applications.active_deployment_id` → `deployments.deployment_id`,
`deployments.application_id` → `applications.application_id`), so the
circular foreign key is broken the same way PL1→PL3 broke
`operations.application_id`: create `deployments` first (its own FKs
point at already-existing tables), then add the back-reference to
`applications` via a separate `ALTER TABLE`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployments",
        sa.Column("deployment_id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "application_id", UUID(as_uuid=False), sa.ForeignKey("applications.application_id"), nullable=False
        ),
        sa.Column("release_id", UUID(as_uuid=False), sa.ForeignKey("releases.release_id"), nullable=False),
        sa.Column(
            "operation_id", UUID(as_uuid=False), sa.ForeignKey("operations.operation_id"), nullable=True
        ),
        sa.Column("verification_status", sa.String, nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column("applications", sa.Column("active_deployment_id", UUID(as_uuid=False), nullable=True))
    op.create_foreign_key(
        "fk_applications_active_deployment_id",
        "applications",
        "deployments",
        ["active_deployment_id"],
        ["deployment_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_applications_active_deployment_id", "applications", type_="foreignkey")
    op.drop_column("applications", "active_deployment_id")
    op.drop_table("deployments")
