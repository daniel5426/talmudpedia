import json

from app.system_artifacts.platform_sdk import handler


class DummyClient:
    base_url = "http://localhost:8000"
    headers = {}


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


def test_execute_requires_explicit_action():
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


def test_execute_rejects_wrapped_json_action_from_value_wrapper():
    wrapped = '{"action":"rag.create_visual_pipeline","payload":{"name":"Vector Search","tenant_slug":"tenant-a","graph_definition":{"nodes":[],"edges":[]}}}'
    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "user_id": "u1",
                "grant_id": "g1",
                "tenant_id": "tenant-1",
                "principal_id": "p1",
                "initiator_user_id": "u1",
                "run_id": "r1",
                "value": wrapped,
            }
        },
    )

    err = out["context"]["errors"][0]
    assert out["context"]["action"] == "rag.create_visual_pipeline"
    assert out["context"]["result"]["reason"] == "non_canonical_input"
    assert err["code"] == "NON_CANONICAL_PLATFORM_SDK_INPUT"
    assert err["source_field"] == "value"
    assert err["attempted_action"] == "rag.create_visual_pipeline"
    assert err["embedded_json_parseable"] is True
    assert "top-level action and payload" in err["message"]


def test_execute_rejects_noncanonical_wrapped_text_input():
    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "tenant_id": "tenant-1",
                "text": '{"action":"agents.get","payload":{"agent_id":"agent-1"}}',
            }
        },
    )

    err = out["context"]["errors"][0]
    assert out["context"]["action"] == "agents.get"
    assert out["context"]["result"]["reason"] == "non_canonical_input"
    assert err["code"] == "NON_CANONICAL_PLATFORM_SDK_INPUT"
    assert err["source_field"] == "text"
    assert err["attempted_action"] == "agents.get"


def test_execute_reports_noncanonical_wrapped_json_as_contract_error():
    malformed = (
        '{"action":"rag.create_visual_pipeline","payload":{"nodes":['
        '{"id":"start","type":"start","config":,"x":100,"y":100}]}}'
    )

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "tenant_id": "tenant-1",
                "value": malformed,
                "query": malformed,
            }
        },
    )

    err = out["context"]["errors"][0]
    assert out["context"]["action"] == "rag.create_visual_pipeline"
    assert out["context"]["result"]["reason"] == "non_canonical_input"
    assert err["code"] == "NON_CANONICAL_PLATFORM_SDK_INPUT"
    assert err["source_field"] == "value"
    assert err["attempted_action"] == "rag.create_visual_pipeline"
    assert err["embedded_json_parseable"] is False
    assert "top-level action and payload" in err["message"]


def test_execute_rejects_deprecated_plan_actions():
    out = handler.execute(
        state={},
        config={},
        context={"inputs": {"action": "validate_plan", "tenant_id": "tenant-1", "token": "t"}},
    )

    assert out["context"]["action"] == "validate_plan"
    assert out["context"]["result"]["reason"] == "deprecated_action"
    assert any(err.get("error") == "deprecated_action" for err in out["context"]["errors"])


def test_execute_reports_unknown_rag_action_explicitly():
    out = handler.execute(
        state={},
        config={},
        context={"inputs": {"action": "rag.nodes.catalog", "tenant_id": "tenant-1", "token": "t"}},
    )

    assert out["context"]["action"] == "rag.nodes.catalog"
    assert out["context"]["result"]["message"] == "Unknown action 'rag.nodes.catalog'."
    assert any(err.get("error") == "unknown_action" for err in out["context"]["errors"])


def test_execute_maps_legacy_alias_to_canonical_action(monkeypatch):
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
    monkeypatch.setattr(handler, "_fetch_catalog", lambda client, payload: ({"ok": True}, []))

    out = handler.execute(
        state={},
        config={},
        context={"inputs": {"action": "fetch_catalog", "tenant_id": "tenant-1", "token": "t"}},
    )

    assert out["context"]["action"] == "catalog.list_capabilities"
    assert out["context"]["result"] == {"ok": True}


def test_execute_maps_create_agent_alias_to_agents_create(monkeypatch):
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
    monkeypatch.setattr(handler, "_control_client", lambda _client: type("C", (), {
        "agents": type("A", (), {
            "create": staticmethod(lambda payload, options=None: {"data": {"id": "agent-1", **payload}})
        })()
    })())

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "create_agent",
                "tenant_id": "tenant-1",
                "payload": {"name": "Support Bot", "slug": "support-bot", "graph_definition": {"nodes": [], "edges": []}},
            }
        },
    )

    assert out["context"]["action"] == "agents.create"
    assert out["context"]["errors"] == []
    assert out["context"]["result"]["id"] == "agent-1"


def test_resolve_action_requires_explicit_action():
    resolved = handler._resolve_action(
        explicit_action=None,
        inputs={"steps": [{"action": "deploy_agent"}]},
        payload={"tests": [{"name": "t1"}], "message": "hello"},
        steps=[{"action": "deploy_agent"}],
        tests=[{"name": "t1"}],
    )
    assert resolved == "noop"
