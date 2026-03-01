from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from artifacts.builtin.platform_sdk import handler


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
        workload_security=_DynamicAPI("workload_security"),
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
        ("rag.list_pipelines", {}, "rag", "list_visual_pipelines", None, None),
        (
            "rag.create_or_update_pipeline",
            {"pipeline_id": "pipe-1", "patch": {"name": "updated"}},
            "rag",
            "update_visual_pipeline",
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
        ("auth.create_delegation_grant", {"subject_id": "u1"}, "auth", "create_delegation_grant", None, None),
        ("workload_security.list_pending", {}, "workload_security", "list_pending_scope_policies", None, None),
        (
            "workload_security.approve_policy",
            {"principal_id": "p1", "approved_scopes": ["tools.write"]},
            "workload_security",
            "approve_scope_policy",
            "p1",
            None,
        ),
        ("workload_security.reject_policy", {"principal_id": "p1"}, "workload_security", "reject_scope_policy", "p1", None),
        (
            "workload_security.list_approvals",
            {"subject_type": "tool", "subject_id": "t1", "action_scope": "tools.delete"},
            "workload_security",
            "list_action_approvals",
            None,
            None,
        ),
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
            "artifacts.promote",
            {"artifact_id": "a1", "namespace": "custom"},
            "artifacts",
            "promote",
            "a1",
            "options",
        ),
        ("artifacts.test", {"request": {"artifact_id": "a1", "input": {}}}, "artifacts", "test", None, None),
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
            "agents.create_or_update",
            {"name": "ag", "slug": "ag"},
            "agents",
            "create",
            None,
            "options",
        ),
        ("agents.publish", {"agent_id": "ag1"}, "agents", "publish", "ag1", "options"),
        ("agents.validate", {"agent_id": "ag1", "validation": {"strict": True}}, "agents", "validate", "ag1", None),
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
        context={"inputs": {"action": action, "tenant_id": "tenant-1", "token": "token", "payload": payload}},
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
                "tenant_id": "tenant-1",
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
                "tenant_id": "tenant-1",
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


def test_dispatch_actions_have_parity_test_coverage():
    handler_text = Path("artifacts/builtin/platform_sdk/handler.py").read_text()
    dispatched = set(re.findall(r'"([a-z_]+\.[a-z_]+)": lambda:', handler_text))

    parity_text = "\n".join(
        Path(p).read_text()
        for p in [
            "tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py",
            "tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py",
            "tests/platform_sdk_tool/test_platform_sdk_actions.py",
            "tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py",
        ]
    )
    covered = set(re.findall(r"([a-z_]+\.[a-z_]+)", parity_text))
    missing = sorted(dispatched - covered)

    assert missing == [], f"Missing parity coverage for actions: {missing}"
