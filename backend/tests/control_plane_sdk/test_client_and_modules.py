from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from talmudpedia_control_sdk import ControlPlaneClient, ControlPlaneSDKError


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any = None,
        headers: Optional[Dict[str, str]] = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self.text = text

    def json(self) -> Any:
        return self._payload


class _RecordingSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[Dict[str, Any]] = []

    def request(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return self.response


def test_mutation_headers_include_contract_tenant_auth_and_idempotency() -> None:
    session = _RecordingSession(_FakeResponse(payload={"id": "tool-1"}))
    client = ControlPlaneClient(
        base_url="http://localhost:8000",
        token="token-123",
        tenant_id="tenant-1",
        session=session,
    )

    envelope = client.tools.create(
        {"name": "T", "slug": "t", "input_schema": {"type": "object"}, "output_schema": {"type": "object"}},
        options={"idempotency_key": "idem-1", "dry_run": True},
    )

    assert envelope["data"]["id"] == "tool-1"
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "http://localhost:8000/tools"
    assert call["params"]["dry_run"] is True
    assert call["headers"]["Authorization"] == "Bearer token-123"
    assert call["headers"]["X-Tenant-ID"] == "tenant-1"
    assert call["headers"]["X-SDK-Contract"] == "1"
    assert call["headers"]["X-Idempotency-Key"] == "idem-1"


def test_envelope_wraps_non_standard_json_response() -> None:
    session = _RecordingSession(_FakeResponse(payload=[{"id": "a1"}], headers={"X-Request-ID": "req-1"}))
    client = ControlPlaneClient(base_url="http://localhost:8000", token="token-123", tenant_id="tenant-1", session=session)
    envelope = client.agents.list()

    assert envelope["data"] == [{"id": "a1"}]
    assert envelope["errors"] == []
    assert envelope["meta"]["request_id"] == "req-1"


def test_error_mapping_uses_structured_body() -> None:
    payload = {"code": "VALIDATION_ERROR", "message": "bad input", "retryable": False}
    session = _RecordingSession(_FakeResponse(status_code=422, payload=payload, text="bad input"))
    client = ControlPlaneClient(base_url="http://localhost:8000", token="token-123", tenant_id="tenant-1", session=session)

    with pytest.raises(ControlPlaneSDKError) as excinfo:
        client.tools.create({"name": "x"})

    err = excinfo.value
    assert err.code == "VALIDATION_ERROR"
    assert err.http_status == 422
    assert err.retryable is False


def test_error_mapping_preserves_structured_detail_and_request_id() -> None:
    payload = {
        "detail": {
            "code": "GRAPH_MUTATION_INTERNAL_ERROR",
            "message": "Agent graph mutation failed due to an internal server error",
            "operation": "agents.graph.apply_patch",
            "phase": "post_write_validation",
            "error_class": "RuntimeError",
        }
    }
    session = _RecordingSession(
        _FakeResponse(
            status_code=500,
            payload=payload,
            headers={"X-Request-ID": "req-sdk-500"},
            text="Internal Server Error",
        )
    )
    client = ControlPlaneClient(base_url="http://localhost:8000", token="token-123", tenant_id="tenant-1", session=session)

    with pytest.raises(ControlPlaneSDKError) as excinfo:
        client.agents.apply_graph_patch("agent-1", [{"op": "set_node_config_value"}])

    err = excinfo.value
    assert err.code == "GRAPH_MUTATION_INTERNAL_ERROR"
    assert err.http_status == 500
    assert err.details is not None
    assert err.details["request_id"] == "req-sdk-500"
    assert err.details["operation"] == "agents.graph.apply_patch"
    assert err.details["phase"] == "post_write_validation"


def test_agents_update_uses_patch_route_by_default() -> None:
    session = _RecordingSession(_FakeResponse(payload={"id": "agent-1"}))
    client = ControlPlaneClient(base_url="http://localhost:8000", token="token-123", tenant_id="tenant-1", session=session)

    client.agents.update("agent-1", {"description": "updated"})

    call = session.calls[0]
    assert call["method"] == "PATCH"
    assert call["url"].endswith("/agents/agent-1")


def test_artifact_publish_serialization_includes_tenant_slug() -> None:
    session = _RecordingSession(_FakeResponse(payload={"artifact_id": "draft-1"}))
    client = ControlPlaneClient(base_url="http://localhost:8000", token="token-123", tenant_id="tenant-1", session=session)

    client.artifacts.publish(
        "draft-1",
        tenant_slug="tenant-a",
        options={"idempotency_key": "idem-promote"},
    )

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/admin/artifacts/draft-1/publish")
    assert call["params"]["tenant_slug"] == "tenant-a"
    assert call["headers"]["X-Idempotency-Key"] == "idem-promote"


def test_tenant_resolver_sets_header_per_request() -> None:
    session = _RecordingSession(_FakeResponse(payload={"id": "agent-1"}))
    resolver_values = iter(["tenant-a", "tenant-b"])
    client = ControlPlaneClient(
        base_url="http://localhost:8000",
        token="token-123",
        tenant_resolver=lambda: next(resolver_values),
        session=session,
    )

    client.agents.get("agent-1")
    client.agents.get("agent-1")

    first = session.calls[0]["headers"]["X-Tenant-ID"]
    second = session.calls[1]["headers"]["X-Tenant-ID"]
    assert first == "tenant-a"
    assert second == "tenant-b"


def test_from_env_uses_default_test_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_BASE_URL", "http://env-host")
    monkeypatch.setenv("TEST_API_KEY", "env-token")
    monkeypatch.setenv("TEST_TENANT_ID", "env-tenant")
    session = _RecordingSession(_FakeResponse(payload={"ok": True}))

    client = ControlPlaneClient.from_env(session=session)
    client.agents.list()

    call = session.calls[0]
    assert call["url"].startswith("http://env-host/")
    assert call["headers"]["Authorization"] == "Bearer env-token"
    assert call["headers"]["X-Tenant-ID"] == "env-tenant"
