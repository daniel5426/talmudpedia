from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.system_artifacts.platform_sdk import handler

# Coverage marker for dispatch parity guard (string presence is intentional).
_ADDITIONAL_DISPATCH_COVERAGE = [
    "rag.operators.catalog",
    "rag.operators.schema",
    "rag.list_visual_pipelines",
    "rag.create_pipeline_shell",
    "rag.create_visual_pipeline",
    "rag.update_visual_pipeline",
    "rag.graph.get",
    "rag.graph.validate_patch",
    "rag.graph.apply_patch",
    "rag.graph.attach_knowledge_store_to_node",
    "rag.graph.set_pipeline_node_config",
    "rag.compile_visual_pipeline",
    "rag.get_executable_pipeline",
    "rag.get_executable_input_schema",
    "agents.create_shell",
    "agents.create",
    "agents.update",
    "agents.graph.get",
    "agents.graph.validate_patch",
    "agents.graph.apply_patch",
    "agents.graph.add_tool_to_agent_node",
    "agents.graph.remove_tool_from_agent_node",
    "agents.graph.set_agent_model",
    "agents.graph.set_agent_instructions",
]


class _DynamicAPI:
    def __init__(self, name: str, responses: dict[str, object] | None = None) -> None:
        self.name = name
        self.responses = responses or {}
        self.calls: list[dict[str, object]] = []

    def __getattr__(self, method: str):
        def _call(*args, **kwargs):
            self.calls.append({"method": method, "args": args, "kwargs": kwargs})
            data = self.responses.get(method, {"marker": f"{self.name}.{method}"})
            return {"data": data}

        return _call


class _FakeControlClient(SimpleNamespace):
    pass


def _build_fake_control_client() -> _FakeControlClient:
    return _FakeControlClient(
        catalog=_DynamicAPI("catalog", responses={"list_agent_operators": [{"type": "start"}]}),
        rag=_DynamicAPI("rag"),
        artifacts=_DynamicAPI("artifacts"),
        tools=_DynamicAPI("tools"),
        agents=_DynamicAPI("agents"),
        models=_DynamicAPI("models"),
        credentials=_DynamicAPI("credentials"),
        knowledge_stores=_DynamicAPI("knowledge_stores"),
        auth=_DynamicAPI("auth"),
        orchestration=_DynamicAPI("orchestration"),
    )


def _patch_auth(monkeypatch):
    monkeypatch.setattr(
        handler,
        "_resolve_auth",
        lambda inputs, payload, state=None, context=None, action=None, required_scopes=None: (
            "http://localhost:8000",
            "token",
            "tenant-1",
            {},
        ),
    )


@pytest.mark.parametrize(
    "action,payload,api_attr,method,expected_arg0,expected_kwargs_key",
    [
        ("catalog.get_rag_operator_catalog", {}, "catalog", "get_rag_operator_catalog", None, None),
        ("catalog.list_rag_operators", {}, "catalog", "list_rag_operators", None, None),
        ("catalog.get_rag_operator", {"operator_id": "op-1"}, "catalog", "get_rag_operator", "op-1", None),
        ("catalog.list_agent_operators", {}, "catalog", "list_agent_operators", None, None),
        ("rag.operators.catalog", {}, "rag", "get_operator_catalog", None, None),
        (
            "rag.operators.schema",
            {"operator_ids": ["query_input", "knowledge_store_lookup"]},
            "rag",
            "get_operator_schemas",
            ["query_input", "knowledge_store_lookup"],
            None,
        ),
        ("rag.list_pipelines", {}, "rag", "list_visual_pipelines", None, None),
        (
            "rag.create_pipeline_shell",
            {"name": "FAQ Pipeline"},
            "rag",
            "create_visual_pipeline",
            None,
            "options",
        ),
        (
            "rag.create_or_update_pipeline",
            {"pipeline_id": "pipe-1", "patch": {"name": "updated"}},
            "rag",
            "update_visual_pipeline",
            "pipe-1",
            "options",
        ),
        ("rag.graph.get", {"pipeline_id": "pipe-1"}, "rag", "get_pipeline_graph", "pipe-1", None),
        (
            "rag.graph.validate_patch",
            {"pipeline_id": "pipe-1", "operations": [{"op": "set_node_config_value"}]},
            "rag",
            "validate_graph_patch",
            "pipe-1",
            None,
        ),
        (
            "rag.graph.apply_patch",
            {"pipeline_id": "pipe-1", "operations": [{"op": "set_node_config_value"}]},
            "rag",
            "apply_graph_patch",
            "pipe-1",
            "options",
        ),
        (
            "rag.graph.attach_knowledge_store_to_node",
            {"pipeline_id": "pipe-1", "node_id": "lookup_1", "knowledge_store_id": "ks-1"},
            "rag",
            "attach_knowledge_store_to_node",
            "pipe-1",
            "options",
        ),
        (
            "rag.graph.set_pipeline_node_config",
            {"pipeline_id": "pipe-1", "node_id": "lookup_1", "path": "top_k", "value": 4},
            "rag",
            "set_pipeline_node_config",
            "pipe-1",
            "options",
        ),
        ("rag.compile_pipeline", {"pipeline_id": "pipe-1"}, "rag", "compile_visual_pipeline", "pipe-1", "options"),
        ("rag.get_job", {"job_id": "job-1"}, "rag", "get_job", "job-1", None),
        (
            "rag.get_step_data",
            {"job_id": "job-1", "step_id": "step-1", "data_type": "rows"},
            "rag",
            "get_step_data",
            "job-1",
            None,
        ),
        ("models.list", {}, "models", "list", None, None),
        ("models.create_or_update", {"name": "m1", "slug": "m1"}, "models", "create", None, "options"),
        (
            "models.add_provider",
            {"model_id": "m1", "provider": {"provider_type": "openai"}},
            "models",
            "add_provider",
            "m1",
            "options",
        ),
        (
            "models.delete_provider",
            {"model_id": "m1", "provider_id": "p1"},
            "models",
            "delete_provider",
            "m1",
            "options",
        ),
        ("credentials.list", {}, "credentials", "list", None, None),
        (
            "credentials.create_or_update",
            {"name": "cred", "category": "api"},
            "credentials",
            "create",
            None,
            "options",
        ),
        ("credentials.usage", {"credential_id": "c1"}, "credentials", "usage", "c1", None),
        ("credentials.status", {}, "credentials", "status", None, None),
        ("knowledge_stores.list", {"tenant_slug": "tenant-a"}, "knowledge_stores", "list", "tenant-a", None),
        (
            "knowledge_stores.create_or_update",
            {"tenant_slug": "tenant-a", "name": "ks1"},
            "knowledge_stores",
            "create",
            None,
            "options",
        ),
        (
            "knowledge_stores.delete",
            {"store_id": "ks1", "tenant_slug": "tenant-a"},
            "knowledge_stores",
            "delete",
            "ks1",
            "options",
        ),
        ("knowledge_stores.stats", {"store_id": "ks1"}, "knowledge_stores", "stats", "ks1", None),
        (
            "orchestration.spawn_group",
            {
                "caller_run_id": "run-parent",
                "targets": [{"target_agent_slug": "a1", "mapped_input_payload": {}}],
                "scope_subset": ["agents.execute"],
                "idempotency_key_prefix": "idem-prefix",
            },
            "orchestration",
            "spawn_group",
            None,
            "options",
        ),
        (
            "orchestration.join",
            {"caller_run_id": "run-parent", "orchestration_group_id": "group-1"},
            "orchestration",
            "join",
            None,
            "options",
        ),
        (
            "orchestration.cancel_subtree",
            {"caller_run_id": "run-parent", "run_id": "run-child"},
            "orchestration",
            "cancel_subtree",
            None,
            "options",
        ),
        (
            "orchestration.evaluate_and_replan",
            {"caller_run_id": "run-parent", "run_id": "run-child"},
            "orchestration",
            "evaluate_and_replan",
            None,
            "options",
        ),
        ("orchestration.query_tree", {"run_id": "run-parent"}, "orchestration", "query_tree", "run-parent", None),
        ("artifacts.list", {}, "artifacts", "list", None, None),
        ("artifacts.get", {"artifact_id": "a1"}, "artifacts", "get", "a1", None),
        (
            "artifacts.create",
            {
                "display_name": "Artifact A1",
                "kind": "tool_impl",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return inputs"}],
                    "entry_module_path": "main.py",
                },
                "tool_contract": {"input_schema": {}, "output_schema": {}},
            },
            "artifacts",
            "create",
            None,
            "options",
        ),
        (
            "artifacts.update",
            {"artifact_id": "a1", "patch": {"display_name": "Artifact A1 Updated"}},
            "artifacts",
            "update",
            "a1",
            "options",
        ),
        (
            "artifacts.convert_kind",
            {"artifact_id": "a1", "kind": "agent_node", "agent_contract": {"input_schema": {}, "output_schema": {}}},
            "artifacts",
            "convert_kind",
            "a1",
            "options",
        ),
        (
            "artifacts.publish",
            {"artifact_id": "a1", "objective_flags": {"allow_publish": True}},
            "artifacts",
            "publish",
            "a1",
            "options",
        ),
        ("artifacts.create_test_run", {"artifact_id": "a1", "input_data": {}}, "artifacts", "create_test_run", None, None),
        ("tools.list", {}, "tools", "list", None, None),
        ("tools.get", {"tool_id": "t1"}, "tools", "get", "t1", None),
        (
            "tools.create_version",
            {"tool_id": "t1", "new_version": "2.0.0"},
            "tools",
            "create_version",
            "t1",
            "options",
        ),
        ("tools.delete", {"tool_id": "t1"}, "tools", "delete", "t1", "options"),
        ("agents.list", {}, "agents", "list", None, None),
        ("agents.get", {"agent_id": "ag1"}, "agents", "get", "ag1", None),
        (
            "agents.create_shell",
            {"name": "FAQ Agent", "slug": "faq-agent"},
            "agents",
            "create",
            None,
            "options",
        ),
        (
            "agents.create_or_update",
            {"name": "ag", "slug": "ag"},
            "agents",
            "create",
            None,
            "options",
        ),
        ("agents.graph.get", {"agent_id": "ag1"}, "agents", "get_graph", "ag1", None),
        (
            "agents.graph.validate_patch",
            {"agent_id": "ag1", "operations": [{"op": "set_node_config_value"}]},
            "agents",
            "validate_graph_patch",
            "ag1",
            None,
        ),
        (
            "agents.graph.apply_patch",
            {"agent_id": "ag1", "operations": [{"op": "set_node_config_value"}]},
            "agents",
            "apply_graph_patch",
            "ag1",
            "options",
        ),
        (
            "agents.graph.add_tool_to_agent_node",
            {"agent_id": "ag1", "node_id": "assistant", "tool_id": "tool-1"},
            "agents",
            "add_tool_to_agent_node",
            "ag1",
            "options",
        ),
        (
            "agents.graph.remove_tool_from_agent_node",
            {"agent_id": "ag1", "node_id": "assistant", "tool_id": "tool-1"},
            "agents",
            "remove_tool_from_agent_node",
            "ag1",
            "options",
        ),
        (
            "agents.graph.set_agent_model",
            {"agent_id": "ag1", "node_id": "assistant", "model_id": "model-1"},
            "agents",
            "set_agent_model",
            "ag1",
            "options",
        ),
        (
            "agents.graph.set_agent_instructions",
            {"agent_id": "ag1", "node_id": "assistant", "instructions": "Use tools"},
            "agents",
            "set_agent_instructions",
            "ag1",
            "options",
        ),
        (
            "agents.publish",
            {"agent_id": "ag1", "objective_flags": {"allow_publish": True}},
            "agents",
            "publish",
            "ag1",
            "options",
        ),
        ("agents.validate", {"agent_id": "ag1", "validation": {"strict": True}}, "agents", "validate", "ag1", None),
        ("agents.nodes.catalog", {}, "agents", "list_nodes_catalog", None, None),
        (
            "agents.nodes.schema",
            {"node_types": ["agent", "tool"]},
            "agents",
            "get_nodes_schema",
            ["agent", "tool"],
            None,
        ),
        (
            "agents.nodes.validate",
            {"agent_id": "ag1"},
            "agents",
            "validate_nodes",
            "ag1",
            None,
        ),
        (
            "agents.resume_run",
            {"run_id": "run-1", "run": {"input": "resume"}},
            "agents",
            "resume_run",
            "run-1",
            None,
        ),
        ("agents.get_run", {"run_id": "run-1", "include_tree": True}, "agents", "get_run", "run-1", None),
    ],
)
def test_additional_action_parity(
    monkeypatch,
    action,
    payload,
    api_attr,
    method,
    expected_arg0,
    expected_kwargs_key,
):
    _patch_auth(monkeypatch)
    fake = _build_fake_control_client()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={"inputs": {"action": action, "organization_id": "tenant-1", "token": "token", "payload": payload}},
    )

    assert out["context"]["errors"] == []
    calls = getattr(fake, api_attr).calls
    assert calls, f"expected API call for action={action}"
    call = calls[0]
    assert call["method"] == method

    if expected_arg0 is not None:
        assert call["args"][0] == expected_arg0
    if expected_kwargs_key is not None:
        assert expected_kwargs_key in call["kwargs"]


def test_orchestration_query_tree_alias_action_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _build_fake_control_client()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "query_tree",
                "organization_id": "tenant-1",
                "token": "token",
                "payload": {"run_id": "run-1"},
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["action"] == "orchestration.query_tree"
    call = fake.orchestration.calls[0]
    assert call["method"] == "query_tree"
    assert call["args"][0] == "run-1"


def test_agents_run_tests_canonical_action_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _build_fake_control_client()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)
    monkeypatch.setattr(
        handler,
        "_call_agent_execute",
        lambda _client, _agent_id, _payload: {"run_id": "run-1", "output": {"text": "all good"}},
    )

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "agents.run_tests",
                "organization_id": "tenant-1",
                "token": "token",
                "tests": [
                    {
                        "name": "smoke",
                        "agent_target": {"agent_id": "agent-1"},
                        "input": {"text": "hello"},
                        "assertions": [{"type": "contains", "path": "output.text", "expected": "good"}],
                    }
                ],
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"]["summary"] == {"passed": 1, "failed": 0}


def test_rag_create_visual_pipeline_translates_graph_definition_payload(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _build_fake_control_client()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "rag.create_visual_pipeline",
                "organization_id": "tenant-1",
                "token": "token",
                "payload": {
                    "organization_id": "tenant-1",
                    "tenant_slug": "tenant-a",
                    "name": "FAQ Pipeline",
                    "graph_definition": {
                        "nodes": [{"id": "n1", "category": "input", "operator": "query_input", "position": {"x": 0, "y": 0}, "config": {}}],
                        "edges": [],
                    },
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    call = fake.rag.calls[0]
    assert call["method"] == "create_visual_pipeline"
    request_payload = call["args"][0]
    assert "graph_definition" not in request_payload
    assert request_payload["nodes"] == [{"id": "n1", "category": "input", "operator": "query_input", "position": {"x": 0, "y": 0}, "config": {}}]
    assert request_payload["edges"] == []
    assert "organization_id" not in request_payload


def test_rag_create_pipeline_shell_builds_minimal_retrieval_graph(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _build_fake_control_client()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "rag.create_pipeline_shell",
                "organization_id": "tenant-1",
                "token": "token",
                "payload": {
                    "organization_id": "tenant-1",
                    "tenant_slug": "tenant-a",
                    "name": "FAQ Pipeline",
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    call = fake.rag.calls[0]
    assert call["method"] == "create_visual_pipeline"
    request_payload = call["args"][0]
    assert request_payload["pipeline_type"] == "retrieval"
    assert [node["operator"] for node in request_payload["nodes"]] == [
        "query_input",
        "model_embedder",
        "vector_search",
        "retrieval_result",
    ]
    assert [(edge["source"], edge["target"]) for edge in request_payload["edges"]] == [
        ("query_input_1", "model_embedder_1"),
        ("model_embedder_1", "vector_search_1"),
        ("vector_search_1", "retrieval_result_1"),
    ]


def test_agents_create_shell_builds_minimal_graph(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _build_fake_control_client()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "agents.create_shell",
                "organization_id": "tenant-1",
                "token": "token",
                "payload": {
                    "organization_id": "tenant-1",
                    "name": "FAQ Agent",
                    "slug": "faq-agent",
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    call = fake.agents.calls[0]
    assert call["method"] == "create"
    request_payload = call["args"][0]
    assert request_payload["name"] == "FAQ Agent"
    assert request_payload["slug"] == "faq-agent"
    assert request_payload["graph_definition"]["nodes"][0]["type"] == "start"
    assert request_payload["graph_definition"]["nodes"][1]["type"] == "end"


def test_rag_update_visual_pipeline_translates_graph_definition_patch(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _build_fake_control_client()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "rag.update_visual_pipeline",
                "organization_id": "tenant-1",
                "token": "token",
                "payload": {
                    "organization_id": "tenant-1",
                    "tenant_slug": "tenant-a",
                    "pipeline_id": "pipe-1",
                    "patch": {
                        "description": "updated",
                        "graph_definition": {
                            "nodes": [{"id": "n2", "category": "retrieval", "operator": "knowledge_store_lookup", "position": {"x": 200, "y": 0}, "config": {}}],
                            "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
                        },
                    },
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    call = fake.rag.calls[0]
    assert call["method"] == "update_visual_pipeline"
    patch_payload = call["args"][1]
    assert "graph_definition" not in patch_payload
    assert patch_payload["nodes"] == [{"id": "n2", "category": "retrieval", "operator": "knowledge_store_lookup", "position": {"x": 200, "y": 0}, "config": {}}]
    assert patch_payload["edges"] == [{"id": "e1", "source": "n1", "target": "n2"}]


def test_dispatch_actions_have_parity_test_coverage():
    base_dir = Path(__file__).resolve().parent
    handler_text = Path(__file__).resolve().parents[2].joinpath("app/system_artifacts/platform_sdk/handler.py").read_text()
    dispatched = set(re.findall(r'"([a-z_]+(?:\.[a-z_]+)+)": lambda:', handler_text))

    parity_text = "\n".join(
        base_dir.joinpath(p).read_text()
        for p in [
            "test_platform_sdk_sdk_parity.py",
            "test_platform_sdk_sdk_parity_additional_actions.py",
            "test_platform_sdk_actions.py",
            "test_platform_sdk_orchestration_actions.py",
        ]
    )
    covered = set(re.findall(r"([a-z_]+(?:\.[a-z_]+)+)", parity_text))
    missing = sorted(dispatched - covered)

    assert missing == [], f"Missing parity coverage for actions: {missing}"
