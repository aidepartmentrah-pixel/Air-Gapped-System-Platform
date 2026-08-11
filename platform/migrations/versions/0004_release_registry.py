"""Release Import and Registry — PL3.

`applications`/`releases`/`release_storage` are the real Platform
Operational Registry (§7.2 Application Identity Rule, §7.3 Release
Identity Rule). `releases` carries a `UNIQUE (application_id, version)`
constraint — the database itself enforces "detect whether the same
application and version already exist" (§3.5 step 14) rather than an
application-level check-then-insert, the same pattern PL1 used for the
operation lock.

Also adds the foreign key from `operations.application_id` to
`applications.application_id` that PL1's migration (`0002`) deliberately
deferred, since `applications` didn't exist yet.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("application_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("slug", sa.String, nullable=False, unique=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "releases",
        sa.Column("release_id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "application_id",
            UUID(as_uuid=False),
            sa.ForeignKey("applications.application_id"),
            nullable=False,
        ),
        sa.Column("version", sa.String, nullable=False),
        sa.Column("contract_version", sa.String, nullable=False),
        sa.Column("manifest_schema_version", sa.String, nullable=False),
        sa.Column("fingerprint", sa.String, nullable=False),
        sa.Column("summary", sa.String, nullable=True),
        sa.Column("manifest", JSONB, nullable=False),
        sa.Column("created_at_engineering", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("application_id", "version", name="uq_releases_application_version"),
    )

    op.create_table(
        "release_storage",
        sa.Column(
            "release_id",
            UUID(as_uuid=False),
            sa.ForeignKey("releases.release_id"),
            primary_key=True,
        ),
        sa.Column("directory_name", sa.String, nullable=False),
        sa.Column("path", sa.String, nullable=False),
        sa.Column("state", sa.String, nullable=False),
        sa.Column("integrity_verified", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_foreign_key(
        "fk_operations_application_id",
        "operations",
        "applications",
        ["application_id"],
        ["application_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_operations_application_id", "operations", type_="foreignkey")
    op.drop_table("release_storage")
    op.drop_table("releases")
    op.drop_table("applications")
