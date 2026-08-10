from rah_platform.errors import DatabaseConnectionError, DockerUnavailableError


def test_error_to_dict_shape():
    error = DockerUnavailableError("Could not reach Docker.", stage="READINESS", details={"reason": "x"})
    d = error.to_dict(request_id="req-1", operation_id=None, log_reference=None)
    assert d == {
        "code": "PLT-DOCKER-001",
        "category": "DOCKER",
        "message": "Could not reach Docker.",
        "stage": "READINESS",
        "retryable": True,
        "details": {"reason": "x"},
        "request_id": "req-1",
        "operation_id": None,
        "log_reference": None,
    }


def test_database_connection_error_code():
    error = DatabaseConnectionError("db down")
    assert error.code == "PLT-DATABASE-003"
    assert error.category == "DATABASE"
    assert error.retryable is True
