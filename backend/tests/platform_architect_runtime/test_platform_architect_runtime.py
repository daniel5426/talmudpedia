from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

from app.system_artifacts.platform_sdk import handler
from app.services.platform_architect_guardrails import (
    PlatformArchitectBlockedError,
    enforce_platform_architect_guardrails,
)
from talmudpedia_control_sdk import ControlPlaneSDKError


def _patch_auth(monkeypatch):
    monkeypatch.setattr(
        handler,
        "_resolve_auth",
        lambda inputs, payload, state=None, context=None, action=None, required_scopes=None: (
            "http://localhost:8000",
            "token",
            handler._resolve_effective_tenant_id(inputs, payload, state, context),
            {},
        ),
    )


@dataclass
class _FakeRagAPI:
    pipelines_by_slug: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    idempotency_to_pipeline_id: Dict[str, str] = field(default_factory=dict)
    compile_failures_remaining: int = 0
    create_error: Dict[str, Any] | None = None
    calls: List[Dict[str, Any]] = field(default_factory=list)

    def get_operator_catalog(self, tenant_slug=None):
        self.calls.append({"method": "get_operator_catalog", "tenant_slug": tenant_slug})
        return {
            "data": {
                "operators": [
                    {
                        "type": "query_input",
                        "title": "Query Input",
                        "category": "input",
                        "description": "Accept a runtime query.",
                        "input_type": "none",
                        "output_type": "query",
                        "required_config_fields": [],
                    }
                ]
            }
        }

    def get_operator_schemas(self, operator_ids, tenant_slug=None):
        self.calls.append({"method": "get_operator_schemas", "operator_ids": list(operator_ids or []), "tenant_slug": tenant_slug})
        return {
            "data": {
                "specs": {
                    str(operator_id): {
                        "type": str(operator_id),
                        "title": str(operator_id),
                        "category": "input",
                        "input_type": "none",
                        "output_type": "query",
                        "config_schema": {"type": "object", "properties": {}, "additionalProperties": True},
                    }
                    for operator_id in list(operator_ids or [])
                },
                "unknown": [],
            }
        }

    def create_visual_pipeline(self, spec, tenant_slug=None, options=None):
        self.calls.append({"method": "create_visual_pipeline", "spec": spec, "tenant_slug": tenant_slug, "options": options})
        if isinstance(self.create_error, dict):
            raise ControlPlaneSDKError(
                code=str(self.create_error.get("code") or "VALIDATION_ERROR"),
                message=str(self.create_error.get("message") or "create failed"),
                http_status=int(self.create_error.get("http_status") or 422),
                retryable=False,
                details=self.create_error.get("details"),
            )
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
    create_error: Dict[str, Any] | None = None

    def create(self, spec, options=None):
        self.calls.append({"method": "create", "spec": spec, "options": options})
        if isinstance(self.create_error, dict):
            raise ControlPlaneSDKError(
                code=str(self.create_error.get("code") or "VALIDATION_ERROR"),
                message=str(self.create_error.get("message") or "create failed"),
                http_status=int(self.create_error.get("http_status") or 422),
                retryable=False,
                details=self.create_error.get("details"),
            )
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
                "organization_id": payload.get("organization_id"),
                "tool_slug": tool_slug,
                "idempotency_key": payload.get("idempotency_key"),
                "request_metadata": payload.get("request_metadata"),
            }
        },
    )["context"]


def _call_with_runtime_tenant(
    action: str,
    payload: Dict[str, Any],
    *,
    tool_slug: str,
    runtime_organization_id: str,
) -> Dict[str, Any]:
    return handler.execute(
        state={},
        config={},
        context={
            "organization_id": runtime_tenant_id,
            "inputs": {
                "action": action,
                "payload": payload,
                "tool_slug": tool_slug,
            },
        },
    )["context"]


def test_direct_tool_loop_happy_path(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    create_pipeline = _call(
        "rag.create_visual_pipeline",
        {
            "organization_id": "tenant-1",
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
            "organization_id": "tenant-1",
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
            "organization_id": "tenant-1",
            "name": "FAQ Agent",
            "slug": "faq-agent",
            "graph_definition": {
                "spec_version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                    {"id": "end", "type": "end", "position": {"x": 200, "y": 0}, "config": {"output_message": "done"}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "end", "type": "control"},
                ],
            },
            "idempotency_key": "idem-agent-1",
            "request_metadata": {"trace_id": "trace-1", "request_id": "req-3"},
        },
        tool_slug="platform-agents",
    )
    agent_id = create_agent["result"]["id"]
    validate_agent = _call(
        "agents.validate",
        {"organization_id": "tenant-1", "agent_id": agent_id, "validation": {"strict": True}},
        tool_slug="platform-agents",
    )
    execute_agent = _call(
        "agents.execute",
        {
            "organization_id": "tenant-1",
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


def test_platform_architect_guardrails_block_repeated_identical_mutation_failures():
    emitted: list[tuple[str, dict[str, Any]]] = []

    class _Emitter:
        def emit_internal_event(self, event_name, data, *, node_id=None, category=None, visibility=None):
            del node_id, category, visibility
            emitted.append((event_name, data))

    node_context = {
        "run_id": "run-1",
        "node_id": "tool-node",
        "state_context": {"agent_system_key": "platform_architect"},
    }
    tool_result = {
        "context": {
            "action": "agents.graph.apply_patch",
            "errors": [
                {
                    "code": "VALIDATION_ERROR",
                    "validation_errors": [{"code": "GRAPH_INVALID", "path": "/graph/edges", "message": "missing"}],
                }
            ],
        }
    }

    for _ in range(4):
        enforce_platform_architect_guardrails(
            builtin_key="platform-agents",
            tool_result=tool_result,
            input_data={"agent_id": "agent-1"},
            node_context=node_context,
            emitter=_Emitter(),
        )

    with pytest.raises(PlatformArchitectBlockedError) as exc_info:
        enforce_platform_architect_guardrails(
            builtin_key="platform-agents",
            tool_result=tool_result,
            input_data={"agent_id": "agent-1"},
            node_context=node_context,
            emitter=_Emitter(),
        )

    assert exc_info.value.blocker["attempted_action"] == "agents.graph.apply_patch"
    assert exc_info.value.blocker["target_resource"] == "agent_id:agent-1"
    assert [name for name, _data in emitted].count("architect.repair_attempted") == 5
    assert any(name == "architect.repair_blocked" for name, _data in emitted)


def test_platform_architect_guardrails_allow_three_retries_for_noncanonical_contract_failures():
    node_context = {
        "run_id": "run-contract",
        "node_id": "tool-node",
        "state_context": {"agent_system_key": "platform_architect"},
    }
    tool_result = {
        "context": {
            "action": "noop",
            "errors": [
                {
                    "code": "NON_CANONICAL_PLATFORM_SDK_INPUT",
                    "message": "bad wrapper",
                    "attempted_action": "agents.create",
                }
            ],
        }
    }

    for _ in range(3):
        enforce_platform_architect_guardrails(
            builtin_key="platform-agents",
            tool_result=tool_result,
            input_data={"query": '{"action":"agents.create","payload":{"name":"demo"}}'},
            node_context=node_context,
            emitter=None,
        )

    with pytest.raises(PlatformArchitectBlockedError) as exc_info:
        enforce_platform_architect_guardrails(
            builtin_key="platform-agents",
            tool_result=tool_result,
            input_data={"query": '{"action":"agents.create","payload":{"name":"demo"}}'},
            node_context=node_context,
            emitter=None,
        )

    assert exc_info.value.blocker["attempted_action"] == "agents.create"
    assert exc_info.value.blocker["normalized_failure_code"] == "NON_CANONICAL_PLATFORM_SDK_INPUT"


def test_platform_architect_guardrails_allow_one_replan_for_unknown_action_then_block():
    node_context = {
        "run_id": "run-unknown-action",
        "node_id": "tool-node",
        "state_context": {"agent_system_key": "platform_architect"},
    }
    tool_result = {
        "context": {
            "action": "rag.nodes.catalog",
            "errors": [{"code": "INVALID_ARGUMENT", "error": "unknown_action", "message": "unsupported"}],
        }
    }

    for _ in range(4):
        enforce_platform_architect_guardrails(
            builtin_key="platform-rag",
            tool_result=tool_result,
            input_data={},
            node_context=node_context,
            emitter=None,
        )

    with pytest.raises(PlatformArchitectBlockedError) as exc_info:
        enforce_platform_architect_guardrails(
            builtin_key="platform-rag",
            tool_result=tool_result,
            input_data={},
            node_context=node_context,
            emitter=None,
        )

    assert exc_info.value.blocker["attempted_action"] == "rag.nodes.catalog"
    assert exc_info.value.blocker["recommended_next_repair_action"].startswith("Consult the advertised platform-rag action schema")


def test_platform_architect_guardrails_preserve_fastapi_validation_details_for_rag_create():
    node_context = {
        "run_id": "run-rag-create-validation",
        "node_id": "tool-node",
        "state_context": {"agent_system_key": "platform_architect"},
    }
    tool_result = {
        "context": {
            "action": "rag.create_visual_pipeline",
            "errors": [
                {
                    "code": "INVALID_ARGUMENT",
                    "details": {
                        "detail": [
                            {"loc": ["body", "nodes", 0, "category"], "msg": "Field required", "type": "missing"},
                            {"loc": ["body", "edges", 0, "id"], "msg": "Field required", "type": "missing"},
                        ]
                    },
                }
            ],
        }
    }

    for _ in range(4):
        enforce_platform_architect_guardrails(
            builtin_key="platform-rag",
            tool_result=tool_result,
            input_data={"payload": {"name": "website_ingestion_pipeline_runtime_url"}},
            node_context=node_context,
            emitter=None,
        )

    with pytest.raises(PlatformArchitectBlockedError) as exc_info:
        enforce_platform_architect_guardrails(
            builtin_key="platform-rag",
            tool_result=tool_result,
            input_data={"payload": {"name": "website_ingestion_pipeline_runtime_url"}},
            node_context=node_context,
            emitter=None,
        )

    assert exc_info.value.blocker["target_resource"] == "name:website_ingestion_pipeline_runtime_url"
    assert exc_info.value.blocker["last_validation_details"] == [
        {"loc": ["body", "nodes", 0, "category"], "msg": "Field required", "type": "missing"},
        {"loc": ["body", "edges", 0, "id"], "msg": "Field required", "type": "missing"},
    ]


def test_direct_tool_loop_repair_path(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    fake.rag.compile_failures_remaining = 1
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    create_pipeline = _call(
        "rag.create_visual_pipeline",
        {
            "organization_id": "tenant-1",
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
            "organization_id": "tenant-1",
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
            "organization_id": "tenant-1",
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
            "organization_id": "tenant-1",
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
            "organization_id": "tenant-1",
            "tool_id": "tool-1",
            "idempotency_key": "idem-tool-pub-1",
            "request_metadata": {"trace_id": "trace-3", "request_id": "req-1"},
        },
        tool_slug="platform-assets",
    )
    blocked_by_approval = _call(
        "tools.publish",
        {
            "organization_id": "tenant-1",
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
        {"organization_id": "tenant-1", "agent_id": "agent-1", "input": "x"},
        tool_slug="platform-rag",
    )

    assert missing_tenant["errors"][0]["code"] == "TENANT_REQUIRED"
    assert scope_denied["errors"][0]["code"] == "SCOPE_DENIED"


def test_platform_sdk_outputs_redacted_auth_context(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    result = _call(
        "models.list",
        {
            "organization_id": "tenant-1",
            "request_metadata": {"trace_id": "trace-auth", "request_id": "req-auth"},
        },
        tool_slug="platform-assets",
    )

    auth_context = result["meta"]["auth_context"]
    assert auth_context["action"] == "models.list"
    assert auth_context["organization_id"] == "tenant-1"
    assert auth_context["runtime_tenant_id"] is None
    assert auth_context["explicit_tenant_id"] == "tenant-1"
    assert auth_context["token_present"] is True
    assert auth_context["required_scopes"] == ["models.read"]
    assert "Authorization" in auth_context["client_header_keys"]
    assert "X-SDK-Contract" in auth_context["client_header_keys"]
    assert "Bearer token" not in str(auth_context)


def test_replay_idempotency_reuses_pipeline(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)
    payload = {
        "organization_id": "tenant-1",
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


def test_agent_create_surfaces_structured_validation_errors(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    fake.agents.create_error = {
        "code": "VALIDATION_ERROR",
        "message": "Graph validation failed",
        "http_status": 422,
        "details": {
            "detail": {
                "error": "validation_error",
                "errors": [
                    {
                        "code": "GRAPH_START_NODE_COUNT_INVALID",
                        "message": "Graph must include exactly one Start node.",
                    }
                ],
            }
        },
    }
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    response = _call(
        "agents.create",
        {
            "organization_id": "tenant-1",
            "name": "Bad Graph Agent",
            "slug": "bad-graph-agent",
            "graph_definition": {"spec_version": "1.0", "nodes": [], "edges": []},
        },
        tool_slug="platform-agents",
    )

    err = response["errors"][0]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["http_status"] == 422
    assert err["details"]["detail"]["error"] == "validation_error"
    assert err["validation_errors"][0]["code"] == "GRAPH_START_NODE_COUNT_INVALID"


def test_rag_create_visual_pipeline_surfaces_structured_validation_errors(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    fake.rag.create_error = {
        "code": "INVALID_ARGUMENT",
        "message": "create failed",
        "http_status": 422,
        "details": {
            "detail": {
                "error": "validation_error",
                "errors": [
                    {"code": "MISSING_FIELD", "path": "nodes[0].category", "message": "Field required"},
                    {"code": "MISSING_FIELD", "path": "edges[0].id", "message": "Field required"},
                ],
            }
        },
    }
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    response = _call(
        "rag.create_visual_pipeline",
        {
            "organization_id": "tenant-1",
            "tenant_slug": "tenant-a",
            "name": "Website Ingest",
            "nodes": [{"id": "start"}],
            "edges": [{"source": "start", "target": "end"}],
        },
        tool_slug="platform-rag",
    )

    err = response["errors"][0]
    assert response["action"] == "rag.create_visual_pipeline"
    assert err["code"] == "INVALID_ARGUMENT"
    assert err["details"]["detail"]["error"] == "validation_error"
    assert err["validation_errors"][0]["path"] == "nodes[0].category"


def test_runtime_tenant_context_satisfies_mutation_without_payload_tenant(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    response = _call_with_runtime_tenant(
        "rag.create_visual_pipeline",
        {
            "tenant_slug": "tenant-a",
            "name": "FAQ Pipeline",
            "slug": "faq-pipeline",
            "graph_definition": {"nodes": [], "edges": []},
        },
        tool_slug="platform-rag",
        runtime_organization_id="tenant-runtime-1",
    )

    assert response["errors"] == []
    assert response["result"]["id"] == "pipe-1"


def test_runtime_tenant_override_is_rejected(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    response = _call_with_runtime_tenant(
        "rag.create_visual_pipeline",
        {
            "organization_id": "tenant-other",
            "tenant_slug": "tenant-a",
            "name": "FAQ Pipeline",
            "slug": "faq-pipeline",
            "graph_definition": {"nodes": [], "edges": []},
        },
        tool_slug="platform-rag",
        runtime_organization_id="tenant-runtime-1",
    )

    assert response["errors"][0]["code"] == "TENANT_MISMATCH"
    assert response["errors"][0]["runtime_tenant_id"] == "tenant-runtime-1"
    assert response["errors"][0]["requested_tenant_id"] == "tenant-other"
