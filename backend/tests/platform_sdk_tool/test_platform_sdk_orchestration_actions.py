from artifacts.builtin.platform_sdk import handler


class DummyClient:
    def __init__(self):
        from types import SimpleNamespace
        self.nodes = SimpleNamespace(catalog={})
        self.agent_nodes = SimpleNamespace(catalog=[])

    base_url = "http://localhost:8000"
    headers = {}


def test_validate_plan_accepts_orchestration_actions():
    client = DummyClient()
    steps = [
        {
            "action": "spawn_run",
            "payload": {
                "caller_run_id": "run-1",
                "target_agent_slug": "agent-a",
                "scope_subset": ["agents.execute"],
                "idempotency_key": "k-1",
            },
        },
        {
            "action": "spawn_group",
            "payload": {
                "caller_run_id": "run-1",
                "scope_subset": ["agents.execute"],
                "idempotency_key_prefix": "g-1",
                "targets": [{"target_agent_slug": "agent-a", "mapped_input_payload": {"input": "x"}}],
            },
        },
        {
            "action": "join",
            "payload": {"caller_run_id": "run-1", "orchestration_group_id": "group-1"},
        },
        {
            "action": "cancel_subtree",
            "payload": {"caller_run_id": "run-1", "run_id": "run-2"},
        },
        {
            "action": "evaluate_and_replan",
            "payload": {"caller_run_id": "run-1", "run_id": "run-2"},
        },
        {
            "action": "query_tree",
            "payload": {"run_id": "run-1"},
        },
    ]

    result, errors = handler._validate_plan(client, steps)

    assert result["valid"] is True
    assert errors == []


def test_orchestration_spawn_run_missing_required_fields():
    result, errors = handler._orchestration_spawn_run(DummyClient(), {}, {"action": "spawn_run"}, dry_run=False)

    assert result is None
    assert errors
    assert errors[0]["error"] == "missing_fields"


def test_execute_dispatches_spawn_run_action(monkeypatch):
    captured = {}

    def fake_resolve_auth(inputs, payload, state=None, context=None, action=None, required_scopes=None):
        return "http://localhost:8000", "token", "tenant-1", {}

    def fake_spawn_run(client, inputs, payload, dry_run):
        captured["inputs"] = inputs
        captured["payload"] = payload
        return {"spawned_run_ids": ["child-1"]}, []

    monkeypatch.setattr(handler, "_resolve_auth", fake_resolve_auth)
    monkeypatch.setattr(handler, "_orchestration_spawn_run", fake_spawn_run)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "spawn_run",
                "caller_run_id": "run-1",
                "target_agent_slug": "agent-a",
                "scope_subset": ["agents.execute"],
                "idempotency_key": "k-1",
            }
        },
    )

    assert out["context"]["action"] == "spawn_run"
    assert out["context"]["errors"] == []
    assert out["context"]["result"]["spawned_run_ids"] == ["child-1"]
    assert captured["inputs"]["idempotency_key"] == "k-1"


def test_query_tree_dry_run():
    result, errors = handler._orchestration_query_tree(
        DummyClient(),
        {"run_id": "run-1"},
        {"run_id": "run-1"},
        dry_run=True,
    )
    assert errors == []
    assert result["status"] == "skipped"
    assert result["dry_run"] is True
