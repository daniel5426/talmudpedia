from __future__ import annotations

import pytest

from app.services.control_plane.contracts import ListQuery, OperationResult
from app.services.control_plane.errors import validation


def test_list_query_parses_canonical_skip_limit_and_view():
    query = ListQuery.from_payload({"limit": 10, "skip": 5, "view": "full"})
    assert query.limit == 10
    assert query.skip == 5
    assert query.view == "full"


def test_list_query_rejects_invalid_limit():
    with pytest.raises(Exception) as exc_info:
        ListQuery.from_payload({"limit": 0})
    error = exc_info.value
    assert getattr(error, "code", None) == "VALIDATION_ERROR"


def test_control_plane_error_payload_is_stable():
    error = validation("Bad input", field="name")
    assert error.to_payload() == {
        "code": "VALIDATION_ERROR",
        "message": "Bad input",
        "http_status": 422,
        "retryable": False,
        "details": {"field": "name"},
    }


def test_operation_result_uses_canonical_operation_shape():
    payload = OperationResult(
        operation_id="op-1",
        kind="agent_run",
        status="queued",
        metadata={"thread_id": "thread-1"},
    ).to_dict()
    assert payload == {
        "operation": {"id": "op-1", "kind": "agent_run", "status": "queued"},
        "metadata": {"thread_id": "thread-1"},
    }
