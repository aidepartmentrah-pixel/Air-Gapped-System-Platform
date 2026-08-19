"""The Generic Operation Framework — PL1.

The common execution model every later state-changing slice (import,
install, update, verify, backup, recover) plugs into, per architecture
§3.1 (Common Operation Lifecycle) and §3.2 (Common Operation States). No
real deployment operation exists yet — PL1 proves the framework using
synthetic test operations only (the proposal is explicit about this: "Do
not implement installation just to test the framework").

The application-operation lock (§7.13) is enforced by the database itself
via a partial unique index on `operations(application_id)` restricted to
`status IN ('PENDING', 'RUNNING')` (see migration `0002`) — acquiring the
lock is just "the INSERT succeeded," releasing it is just "the status
UPDATE moved the row to a terminal state." No separate lock table or
application-level locking logic is needed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from rah_platform.errors import (
    ApplicationLockedError,
    InvalidOperationTransitionError,
    OperationInterruptedError,
    OperationNotFoundError,
    PlatformError,
)
from rah_platform.models import operation_events, operation_logs, operations

logger = logging.getLogger("rah_platform.operations")

TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_sequence(conn, table, operation_id: str) -> int:
    current_max = conn.execute(
        sa.select(sa.func.max(table.c.sequence)).where(table.c.operation_id == operation_id)
    ).scalar()
    return (current_max or 0) + 1


def append_event(
    conn,
    operation_id: str,
    event_type: str,
    *,
    status: str = "INFO",
    message: str = "",
    details: dict | None = None,
) -> None:
    sequence = _next_sequence(conn, operation_events, operation_id)
    conn.execute(
        operation_events.insert().values(
            operation_id=operation_id,
            sequence=sequence,
            event_type=event_type,
            status=status,
            message=message,
            details=details or {},
            occurred_at=_now(),
        )
    )


def log(conn, operation_id: str, message: str, *, level: str = "INFO", details: dict | None = None) -> None:
    """Correlation-aware logging: every log line is both persisted against
    the operation (retrievable via `get_operation_logs`) and emitted
    through standard Python logging with the `operation_id` bound, so it
    also appears correlated in container/stdout logs.
    """
    sequence = _next_sequence(conn, operation_logs, operation_id)
    conn.execute(
        operation_logs.insert().values(
            operation_id=operation_id,
            sequence=sequence,
            level=level,
            message=message,
            details=details or {},
            occurred_at=_now(),
        )
    )
    logger.log(
        getattr(logging, level, logging.INFO),
        "[operation_id=%s] %s",
        operation_id,
        message,
        extra={"operation_id": operation_id, "details": details or {}},
    )


def create_operation(
    engine: Engine,
    *,
    operation_type: str,
    application_id: str,
    requested_by: str,
) -> dict:
    """Every state-changing action creates an operation record before
    performing irreversible work (§7.12 Operation Attempt Rule). The
    record starts as PENDING — an attempt, not yet a success.
    """
    operation_id = str(uuid.uuid4())
    now = _now()
    try:
        with engine.begin() as conn:
            conn.execute(
                operations.insert().values(
                    operation_id=operation_id,
                    operation_type=operation_type,
                    application_id=application_id,
                    status="PENDING",
                    stage=None,
                    requested_by=requested_by,
                    error=None,
                    created_at=now,
                    started_at=None,
                    completed_at=None,
                )
            )
            append_event(conn, operation_id, "REQUEST_ACCEPTED", status="INFO", message="Operation request accepted.")
            log(conn, operation_id, f"Operation {operation_type} created for application {application_id}.")
    except IntegrityError as exc:
        if "ix_operations_active_lock" in str(exc.orig):
            raise ApplicationLockedError(
                "Another operation is already running for this application.",
                stage="REQUEST_ACCEPTED",
                details={"application_id": application_id},
            ) from exc
        raise
    return get_operation(engine, operation_id)


def _require_operation_row(conn, operation_id: str):
    row = conn.execute(operations.select().where(operations.c.operation_id == operation_id)).mappings().first()
    if row is None:
        raise OperationNotFoundError(
            "No operation exists with the given operation_id.",
            details={"operation_id": operation_id},
        )
    return row


def start_operation(engine: Engine, operation_id: str) -> dict:
    with engine.begin() as conn:
        row = _require_operation_row(conn, operation_id)
        if row["status"] != "PENDING":
            raise InvalidOperationTransitionError(
                "Only a PENDING operation can be started.",
                details={"operation_id": operation_id, "current_status": row["status"]},
            )
        conn.execute(
            operations.update()
            .where(operations.c.operation_id == operation_id)
            .values(status="RUNNING", started_at=_now())
        )
        append_event(conn, operation_id, "OPERATION_STARTED", status="INFO", message="Operation execution started.")
        log(conn, operation_id, "Operation started.")
    return get_operation(engine, operation_id)


def update_stage(engine: Engine, operation_id: str, stage: str) -> dict:
    with engine.begin() as conn:
        row = _require_operation_row(conn, operation_id)
        if row["status"] != "RUNNING":
            raise InvalidOperationTransitionError(
                "Stage can only be updated while the operation is RUNNING.",
                details={"operation_id": operation_id, "current_status": row["status"]},
            )
        conn.execute(operations.update().where(operations.c.operation_id == operation_id).values(stage=stage))
        append_event(conn, operation_id, "STAGE_CHANGED", status="INFO", message=f"Stage changed to {stage}.", details={"stage": stage})
    return get_operation(engine, operation_id)


def succeed_operation(engine: Engine, operation_id: str) -> dict:
    with engine.begin() as conn:
        row = _require_operation_row(conn, operation_id)
        if row["status"] != "RUNNING":
            raise InvalidOperationTransitionError(
                "Only a RUNNING operation can succeed.",
                details={"operation_id": operation_id, "current_status": row["status"]},
            )
        conn.execute(
            operations.update()
            .where(operations.c.operation_id == operation_id)
            .values(status="SUCCEEDED", completed_at=_now())
        )
        append_event(conn, operation_id, "OPERATION_COMPLETED", status="PASS", message="Operation completed successfully.")
        log(conn, operation_id, "Operation succeeded.")
    return get_operation(engine, operation_id)


def fail_operation(engine: Engine, operation_id: str, error: PlatformError) -> dict:
    with engine.begin() as conn:
        row = _require_operation_row(conn, operation_id)
        if row["status"] not in ("PENDING", "RUNNING"):
            raise InvalidOperationTransitionError(
                "Only a PENDING or RUNNING operation can fail.",
                details={"operation_id": operation_id, "current_status": row["status"]},
            )
        error_dict = error.to_dict(operation_id=operation_id, log_reference=operation_id)
        conn.execute(
            operations.update()
            .where(operations.c.operation_id == operation_id)
            .values(status="FAILED", completed_at=_now(), error=error_dict)
        )
        append_event(conn, operation_id, "OPERATION_FAILED", status="FAIL", message=error.message, details=error.details)
        log(conn, operation_id, f"Operation failed: {error.message}", level="ERROR", details=error.details)
    return get_operation(engine, operation_id)


def get_operation(engine: Engine, operation_id: str) -> dict:
    with engine.connect() as conn:
        row = _require_operation_row(conn, operation_id)
    return {
        "operation_id": row["operation_id"],
        "operation_type": row["operation_type"],
        "application_id": row["application_id"],
        "status": row["status"],
        "stage": row["stage"],
        "requested_by": row["requested_by"],
        "error": row["error"],
        "created_at": row["created_at"].isoformat(),
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "links": {
            "events": f"/api/v1/operations/{operation_id}/events",
            "logs": f"/api/v1/operations/{operation_id}/logs",
        },
    }


def list_operations(engine: Engine, *, status: str | None = None, limit: int = 50) -> dict:
    """A real, cross-application listing — added for `PL9a`'s Dashboard
    ("Running Operations" count, "Recent Activity" feed), neither of
    which the architecture's own per-application-scoped endpoints could
    honestly answer. Ordered most-recent-first, matching every other
    "recent activity" listing in this codebase.
    """
    query = operations.select().order_by(operations.c.created_at.desc()).limit(limit)
    if status:
        query = query.where(operations.c.status == status)
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
    return {
        "items": [
            {
                "operation_id": row["operation_id"],
                "operation_type": row["operation_type"],
                "application_id": row["application_id"],
                "status": row["status"],
                "stage": row["stage"],
                "requested_by": row["requested_by"],
                "error": row["error"],
                "created_at": row["created_at"].isoformat(),
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "links": {
                    "events": f"/api/v1/operations/{row['operation_id']}/events",
                    "logs": f"/api/v1/operations/{row['operation_id']}/logs",
                },
            }
            for row in rows
        ]
    }


def get_operation_events(engine: Engine, operation_id: str) -> dict:
    with engine.connect() as conn:
        _require_operation_row(conn, operation_id)
        rows = conn.execute(
            operation_events.select()
            .where(operation_events.c.operation_id == operation_id)
            .order_by(operation_events.c.sequence)
        ).mappings().all()
    return {
        "operation_id": operation_id,
        "events": [
            {
                "sequence": r["sequence"],
                "event_type": r["event_type"],
                "status": r["status"],
                "message": r["message"],
                "occurred_at": r["occurred_at"].isoformat(),
                "details": r["details"] or {},
            }
            for r in rows
        ],
    }


def get_operation_logs(engine: Engine, operation_id: str) -> dict:
    with engine.connect() as conn:
        _require_operation_row(conn, operation_id)
        rows = conn.execute(
            operation_logs.select()
            .where(operation_logs.c.operation_id == operation_id)
            .order_by(operation_logs.c.sequence)
        ).mappings().all()
    return {
        "operation_id": operation_id,
        "logs": [
            {
                "sequence": r["sequence"],
                "level": r["level"],
                "message": r["message"],
                "occurred_at": r["occurred_at"].isoformat(),
                "details": r["details"] or {},
            }
            for r in rows
        ],
    }


def mark_stale_operations(engine: Engine, *, older_than: timedelta) -> list[str]:
    """Detects operations left `RUNNING` past the given staleness
    threshold (the backend/process that was executing them stopped
    unexpectedly, per §7.14 Stale Operation Rule) and fails them with
    `PLT-OPERATION-004`, so they don't leave a permanent invisible lock.

    No background worker calls this automatically yet — PL1 has no real
    long-running work to interrupt. It's exposed as a callable so a
    later slice (starting with PL6, the first slice with a process that
    can actually crash mid-operation) can wire it into a periodic check.
    """
    cutoff = _now() - older_than
    with engine.connect() as conn:
        stale_ids = conn.execute(
            sa.select(operations.c.operation_id)
            .where(operations.c.status == "RUNNING")
            .where(operations.c.started_at < cutoff)
        ).scalars().all()

    for operation_id in stale_ids:
        fail_operation(
            engine,
            operation_id,
            OperationInterruptedError(
                "The backend stopped while this operation was running.",
                stage="RUNNING",
                details={"operation_id": operation_id},
            ),
        )
    return list(stale_ids)
