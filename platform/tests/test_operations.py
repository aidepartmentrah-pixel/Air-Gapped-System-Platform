import uuid
from datetime import timedelta

import pytest

from conftest import seed_application
from rah_platform import operations
from rah_platform.errors import (
    ApplicationLockedError,
    DockerUnavailableError,
    InvalidOperationTransitionError,
    OperationNotFoundError,
)


def _new_application_id(db_engine) -> str:
    return seed_application(db_engine)


# --- Operation Creation ---


def test_create_operation_starts_pending(db_engine):
    app_id = _new_application_id(db_engine)
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    assert op["status"] == "PENDING"
    assert op["operation_type"] == "TEST_OPERATION"
    assert op["application_id"] == app_id
    assert op["started_at"] is None
    assert op["completed_at"] is None


# --- Running Transition ---


def test_start_operation_transitions_pending_to_running(db_engine):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    started = operations.start_operation(db_engine, op["operation_id"])
    assert started["status"] == "RUNNING"
    assert started["started_at"] is not None


def test_start_operation_rejects_non_pending(db_engine):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    operations.start_operation(db_engine, op["operation_id"])
    with pytest.raises(InvalidOperationTransitionError):
        operations.start_operation(db_engine, op["operation_id"])


# --- Successful Completion ---


def test_succeed_operation_transitions_running_to_succeeded(db_engine):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    operations.start_operation(db_engine, op["operation_id"])
    result = operations.succeed_operation(db_engine, op["operation_id"])
    assert result["status"] == "SUCCEEDED"
    assert result["completed_at"] is not None


# --- Failed Completion ---


def test_fail_operation_transitions_running_to_failed(db_engine):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    operations.start_operation(db_engine, op["operation_id"])
    error = DockerUnavailableError("Could not reach Docker.", stage="EXECUTING_SCRIPT")
    result = operations.fail_operation(db_engine, op["operation_id"], error)
    assert result["status"] == "FAILED"
    assert result["completed_at"] is not None
    assert result["error"]["code"] == "PLT-DOCKER-001"


# --- Event Ordering ---


def test_events_retain_deterministic_sequence(db_engine):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    operations.start_operation(db_engine, op["operation_id"])
    operations.update_stage(db_engine, op["operation_id"], "EXECUTING_SCRIPT")
    operations.succeed_operation(db_engine, op["operation_id"])

    result = operations.get_operation_events(db_engine, op["operation_id"])
    sequences = [e["sequence"] for e in result["events"]]
    assert sequences == sorted(sequences)
    assert sequences == list(range(1, len(sequences) + 1))
    event_types = [e["event_type"] for e in result["events"]]
    assert event_types == ["REQUEST_ACCEPTED", "OPERATION_STARTED", "STAGE_CHANGED", "OPERATION_COMPLETED"]


# --- Polling ---


def test_get_operation_returns_correct_current_state(db_engine):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    operations.start_operation(db_engine, op["operation_id"])

    polled = operations.get_operation(db_engine, op["operation_id"])
    assert polled["status"] == "RUNNING"
    assert polled["operation_id"] == op["operation_id"]


def test_get_operation_not_found(db_engine):
    with pytest.raises(OperationNotFoundError):
        operations.get_operation(db_engine, str(uuid.uuid4()))


# --- Lock Acquisition / Conflict / Release ---


def test_lock_acquisition_first_operation_succeeds(db_engine):
    app_id = _new_application_id(db_engine)
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    assert op["status"] == "PENDING"


def test_lock_conflict_second_operation_rejected(db_engine):
    app_id = _new_application_id(db_engine)
    operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    with pytest.raises(ApplicationLockedError) as exc_info:
        operations.create_operation(
            db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:other"
        )
    assert exc_info.value.code == "PLT-LOCK-001"


def test_lock_release_on_success_allows_new_operation(db_engine):
    app_id = _new_application_id(db_engine)
    first = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    operations.start_operation(db_engine, first["operation_id"])
    operations.succeed_operation(db_engine, first["operation_id"])

    second = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    assert second["status"] == "PENDING"


def test_lock_release_on_failure_allows_new_operation(db_engine):
    app_id = _new_application_id(db_engine)
    first = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    operations.start_operation(db_engine, first["operation_id"])
    operations.fail_operation(db_engine, first["operation_id"], DockerUnavailableError("down"))

    second = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    assert second["status"] == "PENDING"


def test_lock_is_per_application(db_engine):
    op1 = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    op2 = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    assert op1["status"] == "PENDING"
    assert op2["status"] == "PENDING"


# --- Stale Operation ---


def test_stale_running_operation_marked_failed(db_engine):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    operations.start_operation(db_engine, op["operation_id"])

    # simulate an interrupted worker: the operation has been RUNNING since
    # "before now", so a zero-second staleness threshold immediately
    # qualifies it, without needing to sleep in the test.
    stale_ids = operations.mark_stale_operations(db_engine, older_than=timedelta(seconds=0))
    assert op["operation_id"] in stale_ids

    result = operations.get_operation(db_engine, op["operation_id"])
    assert result["status"] == "FAILED"
    assert result["error"]["code"] == "PLT-OPERATION-004"

    events = operations.get_operation_events(db_engine, op["operation_id"])["events"]
    assert events[-1]["event_type"] == "OPERATION_FAILED"


def test_stale_detection_frees_the_lock(db_engine):
    app_id = _new_application_id(db_engine)
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    operations.start_operation(db_engine, op["operation_id"])
    operations.mark_stale_operations(db_engine, older_than=timedelta(seconds=0))

    # the interrupted operation is now FAILED (terminal), so a new one for
    # the same application is no longer blocked
    new_op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test"
    )
    assert new_op["status"] == "PENDING"


# --- Error Correlation ---


def test_failed_operation_produces_correlated_error(db_engine):
    op = operations.create_operation(
        db_engine, operation_type="TEST_OPERATION", application_id=_new_application_id(db_engine), requested_by="operator:test"
    )
    operations.start_operation(db_engine, op["operation_id"])
    error = DockerUnavailableError("Could not reach Docker.", stage="EXECUTING_SCRIPT")
    result = operations.fail_operation(db_engine, op["operation_id"], error)

    assert result["error"]["operation_id"] == op["operation_id"]
    assert result["error"]["log_reference"] == op["operation_id"]
    assert result["error"]["code"] == "PLT-DOCKER-001"

    logs = operations.get_operation_logs(db_engine, op["operation_id"])["logs"]
    assert any(entry["level"] == "ERROR" and "Could not reach Docker." in entry["message"] for entry in logs)


# --- List Operations (PL9a — Dashboard) ---


def test_list_operations_returns_most_recent_first(db_engine):
    app_id = _new_application_id(db_engine)
    first = operations.create_operation(db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test")
    operations.start_operation(db_engine, first["operation_id"])
    operations.succeed_operation(db_engine, first["operation_id"])

    second_app_id = _new_application_id(db_engine)
    second = operations.create_operation(db_engine, operation_type="TEST_OPERATION", application_id=second_app_id, requested_by="operator:test")

    result = operations.list_operations(db_engine)
    ids_in_order = [item["operation_id"] for item in result["items"]]
    assert ids_in_order.index(second["operation_id"]) < ids_in_order.index(first["operation_id"])


def test_list_operations_filters_by_status(db_engine):
    app_id = _new_application_id(db_engine)
    running = operations.create_operation(db_engine, operation_type="TEST_OPERATION", application_id=app_id, requested_by="operator:test")
    operations.start_operation(db_engine, running["operation_id"])

    other_app_id = _new_application_id(db_engine)
    pending = operations.create_operation(db_engine, operation_type="TEST_OPERATION", application_id=other_app_id, requested_by="operator:test")

    result = operations.list_operations(db_engine, status="RUNNING")
    ids = [item["operation_id"] for item in result["items"]]
    assert running["operation_id"] in ids
    assert pending["operation_id"] not in ids
