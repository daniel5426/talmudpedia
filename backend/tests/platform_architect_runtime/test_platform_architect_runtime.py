from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from artifacts.builtin.platform_sdk import handler
from talmudpedia_control_sdk import ControlPlaneSDKError


def _patch_auth(monkeypatch):
    monkeypatch.setattr(
        handler,
        "_resolve_auth",
        lambda inputs, payload, state=None, context=None, action=None, required_scopes=None: (
            "http://localhost:8000",
            "token",
            payload.get("tenant_id") or inputs.get("tenant_id"),
            {},
        ),
    )


@dataclass
class _FakeRagAPI:
    pipelines_by_slug: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    idempotency_to_pipeline_id: Dict[str, str] = field(default_factory=dict)
    compile_failures_remaining: int = 0
    calls: List[Dict[str, Any]] = field(default_factory=list)

    def create_visual_pipeline(self, spec, tenant_slug=None, options=None):
        self.calls.append({"method": "create_visual_pipeline", "spec": spec, "tenant_slug": tenant_slug, "options": options})
        idem = (options or {}).get("idempotency_key")
        slug = str(spec.get("slug") or f"pipeline-{len(self.pipelines_by_slug) + 1}")
        if idem and idem in self.idempotency_to_pipeline_id:
            existing_id = self.idempotency_to_pipeline_id[idem]
            for rec in self.pipelines_by_slug.values():
                if str(rec.get("id")) == existing_id:
                    return {"data": rec}
        pipeline_id = f"pipe-{len(self.pipelines_by_slug) + 1}"
        rec = {"id": pipeline_id, "slug": slug, **spec}
        self.pipelines_by_slug[slug] = rec
        if idem:
            self.idempotency_to_pipeline_id[idem] = pipeline_id
        return {"data": rec}

    def update_visual_pipeline(self, pipeline_id, patch, tenant_slug=None, options=None):
        self.calls.append({"method": "update_visual_pipeline", "pipeline_id": pipeline_id, "patch": patch, "tenant_slug": tenant_slug, "options": options})
        for slug, rec in self.pipelines_by_slug.items():
            if str(rec.get("id")) == str(pipeline_id):
                rec.update(patch)
                self.pipelines_by_slug[slug] = rec
                return {"data": rec}
        return {"data": {"id": pipeline_id, **patch}}

    def compile_visual_pipeline(self, pipeline_id, tenant_slug=None, options=None):
        self.calls.append({"method": "compile_visual_pipeline", "pipeline_id": pipeline_id, "tenant_slug": tenant_slug, "options": options})
        if self.compile_failures_remaining > 0:
            self.compile_failures_remaining -= 1
            raise ControlPlaneSDKError(
                code="VALIDATION_ERROR",
                message="compile failed",
                http_status=422,
                retryable=False,
            )
        return {"data": {"pipeline_id": pipeline_id, "status": "compiled"}}


@dataclass
class _FakeAgentsAPI:
    calls: List[Dict[str, Any]] = field(default_factory=list)
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def create(self, spec, options=None):
        self.calls.append({"method": "create", "spec": spec, "options": options})
        agent_id = f"agent-{len(self.agents) + 1}"
        rec = {"id": agent_id, **spec}
        self.agents[agent_id] = rec
        return {"data": rec}

    def validate(self, agent_id, payload=None):
        self.calls.append({"method": "validate", "agent_id": agent_id, "payload": payload})
        return {"data": {"valid": True, "agent_id": agent_id}}

    def execute(self, agent_id, payload):
        self.calls.append({"method": "execute", "agent_id": agent_id, "payload": payload})
        return {"data": {"run_id": "run-1", "output": {"text": "ok"}}}


@dataclass
class _FakeToolsAPI:
    calls: List[Dict[str, Any]] = field(default_factory=list)
    publish_blocked: bool = False

    def publish(self, tool_id, options=None):
        self.calls.append({"method": "publish", "tool_id": tool_id, "options": options})
        if self.publish_blocked:
            raise ControlPlaneSDKError(
                code="SENSITIVE_ACTION_APPROVAL_REQUIRED",
                message="approval required",
                http_status=403,
                retryable=False,
            )
        return {"data": {"id": tool_id, "status": "published"}}


@dataclass
class _FakeControlClient:
    rag: _FakeRagAPI = field(default_factory=_FakeRagAPI)
    agents: _FakeAgentsAPI = field(default_factory=_FakeAgentsAPI)
    tools: _FakeToolsAPI = field(default_factory=_FakeToolsAPI)


def _call(action: str, payload: Dict[str, Any], *, tool_slug: str) -> Dict[str, Any]:
    return handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": action,
                "payload": payload,
                "tenant_id": payload.get("tenant_id"),
                "tool_slug": tool_slug,
                "idempotency_key": payload.get("idempotency_key"),
                "request_metadata": payload.get("request_metadata"),
            }
        },
    )["context"]


def test_direct_tool_loop_happy_path(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    create_pipeline = _call(
        "rag.create_visual_pipeline",
        {
            "tenant_id": "tenant-1",
            "tenant_slug": "tenant-a",
            "name": "FAQ Pipeline",
            "slug": "faq-pipeline",
            "graph_definition": {"nodes": [], "edges": []},
            "idempotency_key": "idem-pipe-1",
            "request_metadata": {"trace_id": "trace-1", "request_id": "req-1"},
        },
        tool_slug="platform-rag",
    )
    pipeline_id = create_pipeline["result"]["id"]
    compile_pipeline = _call(
        "rag.compile_visual_pipeline",
        {
            "tenant_id": "tenant-1",
            "tenant_slug": "tenant-a",
            "pipeline_id": pipeline_id,
            "idempotency_key": "idem-pipe-compile-1",
            "request_metadata": {"trace_id": "trace-1", "request_id": "req-2"},
        },
        tool_slug="platform-rag",
    )
    create_agent = _call(
        "agents.create",
        {
            "tenant_id": "tenant-1",
            "name": "FAQ Agent",
            "slug": "faq-agent",
            "graph_definition": {"nodes": [], "edges": []},
            "idempotency_key": "idem-agent-1",
            "request_metadata": {"trace_id": "trace-1", "request_id": "req-3"},
        },
        tool_slug="platform-agents",
    )
    agent_id = create_agent["result"]["id"]
    validate_agent = _call(
        "agents.validate",
        {"tenant_id": "tenant-1", "agent_id": agent_id, "validation": {"strict": True}},
        tool_slug="platform-agents",
    )
    execute_agent = _call(
        "agents.execute",
        {
            "tenant_id": "tenant-1",
            "agent_id": agent_id,
            "input": "health-check",
            "idempotency_key": "idem-exec-1",
            "request_metadata": {"trace_id": "trace-1", "request_id": "req-4"},
        },
        tool_slug="platform-agents",
    )

    assert create_pipeline["errors"] == []
    assert compile_pipeline["errors"] == []
    assert create_agent["errors"] == []
    assert validate_agent["errors"] == []
    assert execute_agent["errors"] == []
    assert create_pipeline["meta"]["idempotency_provided"] is True
    assert create_agent["meta"]["idempotency_provided"] is True


def test_direct_tool_loop_repair_path(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    fake.rag.compile_failures_remaining = 1
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    create_pipeline = _call(
        "rag.create_visual_pipeline",
        {
            "tenant_id": "tenant-1",
            "tenant_slug": "tenant-a",
            "name": "FAQ Pipeline",
            "slug": "faq-pipeline",
            "graph_definition": {"nodes": [], "edges": []},
            "idempotency_key": "idem-pipe-2",
            "request_metadata": {"trace_id": "trace-2", "request_id": "req-1"},
        },
        tool_slug="platform-rag",
    )
    pipeline_id = create_pipeline["result"]["id"]

    first_compile = _call(
        "rag.compile_visual_pipeline",
        {
            "tenant_id": "tenant-1",
            "tenant_slug": "tenant-a",
            "pipeline_id": pipeline_id,
            "idempotency_key": "idem-pipe-compile-2",
            "request_metadata": {"trace_id": "trace-2", "request_id": "req-2"},
        },
        tool_slug="platform-rag",
    )
    patch_step = _call(
        "rag.update_visual_pipeline",
        {
            "tenant_id": "tenant-1",
            "tenant_slug": "tenant-a",
            "pipeline_id": pipeline_id,
            "patch": {"description": "repair patch"},
            "idempotency_key": "idem-pipe-patch-2",
            "request_metadata": {"trace_id": "trace-2", "request_id": "req-3"},
        },
        tool_slug="platform-rag",
    )
    second_compile = _call(
        "rag.compile_visual_pipeline",
        {
            "tenant_id": "tenant-1",
            "tenant_slug": "tenant-a",
            "pipeline_id": pipeline_id,
            "idempotency_key": "idem-pipe-compile-3",
            "request_metadata": {"trace_id": "trace-2", "request_id": "req-4"},
        },
        tool_slug="platform-rag",
    )

    assert first_compile["errors"][0]["code"] == "VALIDATION_ERROR"
    assert patch_step["errors"] == []
    assert second_compile["errors"] == []


def test_approval_block_and_draft_first_policy(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    fake.tools.publish_blocked = True
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    blocked_by_policy = _call(
        "tools.publish",
        {
            "tenant_id": "tenant-1",
            "tool_id": "tool-1",
            "idempotency_key": "idem-tool-pub-1",
            "request_metadata": {"trace_id": "trace-3", "request_id": "req-1"},
        },
        tool_slug="platform-assets",
    )
    blocked_by_approval = _call(
        "tools.publish",
        {
            "tenant_id": "tenant-1",
            "tool_id": "tool-1",
            "objective_flags": {"allow_publish": True},
            "idempotency_key": "idem-tool-pub-2",
            "request_metadata": {"trace_id": "trace-3", "request_id": "req-2"},
        },
        tool_slug="platform-assets",
    )

    assert blocked_by_policy["errors"][0]["code"] == "DRAFT_FIRST_POLICY_DENIED"
    assert blocked_by_approval["result"]["status"] == "blocked_approval"
    assert any(err["code"] == "SENSITIVE_ACTION_APPROVAL_REQUIRED" for err in blocked_by_approval["errors"])


def test_tenant_and_scope_denial_paths(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    missing_tenant = _call(
        "rag.create_visual_pipeline",
        {
            "tenant_slug": "tenant-a",
            "name": "FAQ Pipeline",
            "slug": "faq-pipeline",
            "graph_definition": {"nodes": [], "edges": []},
            "idempotency_key": "idem-missing-tenant",
            "request_metadata": {"trace_id": "trace-4", "request_id": "req-1"},
        },
        tool_slug="platform-rag",
    )
    scope_denied = _call(
        "agents.execute",
        {"tenant_id": "tenant-1", "agent_id": "agent-1", "input": "x"},
        tool_slug="platform-rag",
    )

    assert missing_tenant["errors"][0]["code"] == "TENANT_REQUIRED"
    assert scope_denied["errors"][0]["code"] == "SCOPE_DENIED"


def test_replay_idempotency_reuses_pipeline(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)
    payload = {
        "tenant_id": "tenant-1",
        "tenant_slug": "tenant-a",
        "name": "FAQ Pipeline",
        "slug": "faq-pipeline",
        "graph_definition": {"nodes": [], "edges": []},
        "idempotency_key": "idem-replay-pipeline",
        "request_metadata": {"trace_id": "trace-5", "request_id": "req-1"},
    }

    first = _call("rag.create_visual_pipeline", dict(payload), tool_slug="platform-rag")
    second = _call("rag.create_visual_pipeline", dict(payload), tool_slug="platform-rag")

    assert first["errors"] == []
    assert second["errors"] == []
    assert first["result"]["id"] == second["result"]["id"]
    assert len(fake.rag.pipelines_by_slug) == 1
