import json
from types import SimpleNamespace

from artifacts.builtin.platform_sdk import handler


class DummyClient:
    def __init__(self):
        self.nodes = SimpleNamespace(catalog={})
        self.agent_nodes = SimpleNamespace(catalog=[])

    def connect(self):
        return None


def test_validate_plan_accepts_new_actions():
    client = DummyClient()
    steps = [
        {
            "action": "create_artifact_draft",
            "payload": {"name": "demo", "python_code": "def execute(x, y=None):\n    return x"},
        },
        {"action": "promote_artifact", "payload": {"artifact_id": "draft-123", "namespace": "custom"}},
        {
            "action": "create_tool",
            "payload": {
                "name": "Demo Tool",
                "slug": "demo-tool",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
            },
        },
        {"action": "run_tests", "payload": {"tests": [{"name": "t1", "agent_target": {"agent_id": "a"}}]}},
    ]

    result, errors = handler._validate_plan(client, steps)

    assert result["valid"] is True
    assert errors == []


def test_validate_plan_missing_fields_create_tool():
    client = DummyClient()
    steps = [{"action": "create_tool", "payload": {"name": "Tool"}}]
    result, errors = handler._validate_plan(client, steps)

    assert result["valid"] is False
    assert any(err.get("error") == "missing_fields" for err in errors)


def test_run_tests_evaluates_assertions(monkeypatch):
    def fake_call(_client, _agent_id, _payload):
        return {"run_id": "run-1", "output": {"text": json.dumps({"answer": "hello world"})}}

    monkeypatch.setattr(handler, "_call_agent_execute", fake_call)

    tests = [
        {
            "name": "t1",
            "agent_target": {"agent_id": "agent-1"},
            "input": {"text": "hi"},
            "assertions": [
                {"type": "contains", "path": "output.text", "expected": "hello"},
                {"type": "jsonpath", "path": "output.json.answer", "expected": "hello world"},
            ],
        }
    ]

    result, errors = handler._run_tests(DummyClient(), tests, dry_run=False)

    assert errors == []
    assert result["summary"]["passed"] == 1
    assert result["summary"]["failed"] == 0


def test_execute_ignores_auth_envelope_without_action():
    context = {
        "inputs": {
            "user_id": "u1",
            "grant_id": "g1",
            "tenant_id": "t1",
            "principal_id": "p1",
            "requested_scopes": ["*"],
            "initiator_user_id": "u1",
            "run_id": "r1",
            "value": "",
        }
    }
    out = handler.execute(state={}, config={}, context=context)
    assert out["context"]["action"] == "noop"
    assert out["context"]["result"]["status"] == "validation_error"
    assert any(err.get("error") == "missing_action" for err in out["context"]["errors"])
    assert any(err.get("code") == "MISSING_REQUIRED_FIELD" for err in out["context"]["errors"])


def test_execute_ignores_metadata_probe_without_action():
    context = {
        "inputs": {
            "artifact_id": "builtin/platform_sdk",
            "version": "1.0.0",
            "config_keys": ["tool_id", "_artifact_id", "_artifact_version"],
        }
    }
    out = handler.execute(state={}, config={}, context=context)
    assert out["context"]["action"] == "noop"
    assert out["context"]["result"]["status"] == "validation_error"


def test_resolve_action_requires_explicit_action():
    resolved = handler._resolve_action(
        explicit_action=None,
        inputs={"steps": [{"action": "deploy_agent"}]},
        payload={"tests": [{"name": "t1"}], "message": "hello"},
        steps=[{"action": "deploy_agent"}],
        tests=[{"name": "t1"}],
    )
    assert resolved == "noop"


def test_deploy_agent_uses_agents_endpoint_without_fallback(monkeypatch):
    class FakeAgents:
        def __init__(self):
            self.calls = []

        def create(self, payload, options=None):
            self.calls.append({"payload": payload, "options": options})
            return {"data": {"id": "agent-123"}}

    class FakeControlClient:
        def __init__(self):
            self.agents = FakeAgents()

    fake_client = FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _legacy_client: fake_client)

    legacy_client = type("LegacyClient", (), {"base_url": "http://localhost:8000", "headers": {}})()
    step = {"action": "deploy_agent", "payload": {"name": "A", "slug": "a", "graph_definition": {"nodes": [], "edges": []}}}
    result, errors = handler._step_deploy_agent(legacy_client, step, dry_run=False)

    assert errors is None
    assert result == {"id": "agent-123"}
    assert len(fake_client.agents.calls) == 1
