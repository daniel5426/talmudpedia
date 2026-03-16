from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Optional

from talmudpedia_control_sdk import ControlPlaneClient


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


def _client_with_session(session: _RecordingSession) -> ControlPlaneClient:
    return ControlPlaneClient(
        base_url="http://localhost:8000",
        token="token-123",
        tenant_id="tenant-1",
        session=session,
    )


def test_catalog_list_agent_operators_uses_agents_operators_route() -> None:
    session = _RecordingSession(_FakeResponse(payload=[{"type": "start"}]))
    client = _client_with_session(session)

    envelope = client.catalog.list_agent_operators()

    assert envelope["data"] == [{"type": "start"}]
    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/agents/operators")


def test_agents_nodes_routes_use_expected_paths() -> None:
    session = _RecordingSession(_FakeResponse(payload={"ok": True}))
    client = _client_with_session(session)

    client.agents.list_nodes_catalog()
    client.agents.get_nodes_schema(["agent", "tool"])
    client.agents.validate_nodes("agent-1")

    first = session.calls[0]
    second = session.calls[1]
    third = session.calls[2]
    assert first["method"] == "GET"
    assert first["url"].endswith("/agents/nodes/catalog")
    assert second["method"] == "POST"
    assert second["url"].endswith("/agents/nodes/schema")
    assert second["json"]["node_types"] == ["agent", "tool"]
    assert third["method"] == "POST"
    assert third["url"].endswith("/agents/agent-1/validate")


def test_rag_upload_input_file_serialization() -> None:
    session = _RecordingSession(_FakeResponse(payload={"path": "uploads/demo.txt"}))
    client = _client_with_session(session)

    file_obj = BytesIO(b"hello")
    client.rag.upload_input_file("demo.txt", file_obj, tenant_slug="tenant-a")

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/admin/pipelines/pipeline-inputs/upload")
    assert call["params"]["tenant_slug"] == "tenant-a"
    assert "file" in call["files"]
    assert call["files"]["file"][0] == "demo.txt"


def test_rag_list_jobs_filter_serialization() -> None:
    session = _RecordingSession(_FakeResponse(payload={"jobs": []}))
    client = _client_with_session(session)

    client.rag.list_jobs(
        executable_pipeline_id="exec-1",
        visual_pipeline_id="visual-1",
        status="running",
        skip=5,
        limit=10,
        tenant_slug="tenant-a",
    )

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/admin/pipelines/jobs")
    assert call["params"] == {
        "skip": 5,
        "limit": 10,
        "executable_pipeline_id": "exec-1",
        "visual_pipeline_id": "visual-1",
        "status": "running",
        "tenant_slug": "tenant-a",
    }


def test_models_provider_routes_use_expected_methods() -> None:
    session = _RecordingSession(_FakeResponse(payload={"id": "provider-1"}))
    client = _client_with_session(session)

    client.models.update_provider("model-1", "provider-1", {"priority": 2})

    call = session.calls[0]
    assert call["method"] == "PATCH"
    assert call["url"].endswith("/models/model-1/providers/provider-1")
    assert "X-Idempotency-Key" in call["headers"]


def test_credentials_delete_uses_force_disconnect_query() -> None:
    session = _RecordingSession(_FakeResponse(payload={"status": "deleted"}))
    client = _client_with_session(session)

    client.credentials.delete("cred-1", force_disconnect=True)

    call = session.calls[0]
    assert call["method"] == "DELETE"
    assert call["url"].endswith("/admin/settings/credentials/cred-1")
    assert call["params"]["force_disconnect"] is True


def test_knowledge_stores_routes_include_tenant_slug_and_patch_method() -> None:
    session = _RecordingSession(_FakeResponse(payload={"id": "store-1"}))
    client = _client_with_session(session)

    client.knowledge_stores.update("store-1", {"name": "Updated"}, tenant_slug="tenant-a")

    call = session.calls[0]
    assert call["method"] == "PATCH"
    assert call["url"].endswith("/admin/knowledge-stores/store-1")
    assert call["params"]["tenant_slug"] == "tenant-a"


def test_auth_and_orchestration_routes() -> None:
    session = _RecordingSession(_FakeResponse(payload={"ok": True}))
    client = _client_with_session(session)

    client.auth.get_workload_jwks()
    client.orchestration.query_tree("run-1")

    first = session.calls[0]
    second = session.calls[1]
    assert first["method"] == "GET"
    assert first["url"].endswith("/.well-known/jwks.json")
    assert second["method"] == "GET"
    assert second["url"].endswith("/internal/orchestration/runs/run-1/tree")


def test_workload_security_action_routes() -> None:
    session = _RecordingSession(_FakeResponse(payload={"status": "approved"}))
    client = _client_with_session(session)

    client.workload_security.list_action_approvals(
        subject_type="tool",
        subject_id="tool-1",
        action_scope="tools.delete",
    )
    client.workload_security.decide_action_approval(
        {
            "subject_type": "tool",
            "subject_id": "tool-1",
            "action_scope": "tools.delete",
            "status": "approved",
        }
    )

    list_call = session.calls[0]
    decide_call = session.calls[1]
    assert list_call["method"] == "GET"
    assert list_call["url"].endswith("/admin/security/workloads/approvals")
    assert list_call["params"] == {
        "subject_type": "tool",
        "subject_id": "tool-1",
        "action_scope": "tools.delete",
    }
    assert decide_call["method"] == "POST"
    assert decide_call["url"].endswith("/admin/security/workloads/approvals/decide")
    assert "X-Idempotency-Key" in decide_call["headers"]


def test_embedded_agent_routes_use_public_embed_contract() -> None:
    session = _RecordingSession(_FakeResponse(payload={"items": [], "total": 0}))
    client = _client_with_session(session)

    client.embedded_agents.list_agent_threads(
        "agent-1",
        external_user_id="user-1",
        external_session_id="session-1",
        skip=2,
        limit=5,
    )
    client.embedded_agents.get_agent_thread(
        "agent-1",
        "thread-1",
        external_user_id="user-1",
        external_session_id="session-1",
    )
    client.embedded_agents.stream_agent(
        "agent-1",
        {
            "input": "hello",
            "external_user_id": "user-1",
        },
    )

    list_call = session.calls[0]
    detail_call = session.calls[1]
    stream_call = session.calls[2]
    assert list_call["method"] == "GET"
    assert list_call["url"].endswith("/public/embed/agents/agent-1/threads")
    assert list_call["params"] == {
        "external_user_id": "user-1",
        "external_session_id": "session-1",
        "skip": 2,
        "limit": 5,
    }
    assert detail_call["method"] == "GET"
    assert detail_call["url"].endswith("/public/embed/agents/agent-1/threads/thread-1")
    assert detail_call["params"] == {
        "external_user_id": "user-1",
        "external_session_id": "session-1",
    }
    assert stream_call["method"] == "POST"
    assert stream_call["url"].endswith("/public/embed/agents/agent-1/chat/stream")
    assert stream_call["json"] == {
        "input": "hello",
        "external_user_id": "user-1",
    }
