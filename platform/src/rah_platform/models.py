"""Registry table definitions — PL1 introduces `operations`,
`operation_events`, and `operation_logs`. PL2 adds `release_candidates` —
bookkeeping about what `scan_releases` has physically seen in Release
Storage, not a registration of an Application or Release (§7.5 Discovery/
Import/Deployment Separation: "Discovering a Release does not import
it"). PL3 adds `applications`/`releases`/`release_storage` — the real
Registry — and finally adds the foreign key from
`operations.application_id` that PL1 deferred (migration `0004`). PL4
adds `deployments` and `applications.active_deployment_id` (migration
`0005`) — the schema `get_active_deployment`/`get_available_actions`
read from, per §5.14's `operation_id`/`deployment_id` distinction. No
real installation exists until `PL6`, so nothing writes `deployments` for
real yet; `PL4`'s own tests seed it directly to exercise the
already-installed decision paths. PL5 adds `deployment_configuration`
(migration `0006`) — the persisted, deployment-specific configuration
values that `prepare_update`'s "preserve existing configuration" (§7.15
Configuration Preservation Rule) reads from. Secret values are never
stored in plaintext here: `value` stays null for `secret=true` rows,
`secret_reference` holds a stand-in only (§7.16 Secret-State Rule — "the
Operational Registry may store: Secret exists, Secret reference, Secret
source", never the real value). PL6 introduces no new tables — it only
writes to `deployments`/`deployment_configuration`. PL7 adds
`verification_runs`/`verification_checks` (every verification run
preserved independently, per §7.25) and `reconciliations` (recorded drift
findings, per §7.27) — migration `0007`. PL8a adds `backups` — every
backup's own storage location, checksum, and artifact-lifecycle status
(`PENDING`/`CREATED`/`FAILED`/`VERIFIED`/`RESTORED`), deliberately kept
separate from `operations.status` since a backup's own status continues
to change after its creating operation has already reached a terminal
state (e.g. verified later by a different operation) — migration `0008`.
A backup taken as the mandatory pre-update step shares its `operation_id`
with the parent UPDATE operation rather than getting its own (the same
"shared operation for sub-steps" pattern the architecture documents);
a standalone `POST .../backups` call gets its own dedicated BACKUP
operation.

Plain SQLAlchemy Core `Table` objects, not the ORM — access patterns so
far are simple enough (a handful of inserts/selects per call) that a
declarative layer would add ceremony without buying anything yet.
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
    sa.Column("application_id", UUID(as_uuid=False), sa.ForeignKey("applications.application_id"), nullable=False),
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

release_candidates = sa.Table(
    "release_candidates",
    metadata,
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

applications = sa.Table(
    "applications",
    metadata,
    sa.Column("application_id", UUID(as_uuid=False), primary_key=True),
    sa.Column("slug", sa.String, nullable=False, unique=True),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("description", sa.String, nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column(
        "active_deployment_id",
        UUID(as_uuid=False),
        sa.ForeignKey("deployments.deployment_id"),
        nullable=True,
    ),
)

releases = sa.Table(
    "releases",
    metadata,
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

deployments = sa.Table(
    "deployments",
    metadata,
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

deployment_configuration = sa.Table(
    "deployment_configuration",
    metadata,
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

verification_runs = sa.Table(
    "verification_runs",
    metadata,
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

verification_checks = sa.Table(
    "verification_checks",
    metadata,
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

reconciliations = sa.Table(
    "reconciliations",
    metadata,
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

backups = sa.Table(
    "backups",
    metadata,
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

release_storage = sa.Table(
    "release_storage",
    metadata,
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
