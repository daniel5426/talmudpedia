from app.system_artifacts.platform_sdk import handler


class DummyClient:
    base_url = "http://localhost:8000"
    headers = {}


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
        captured["dry_run"] = dry_run
        return {"spawned_run_ids": ["child-1"]}, []

    monkeypatch.setattr(handler, "_resolve_auth", fake_resolve_auth)
    monkeypatch.setattr(handler, "_orchestration_spawn_run", fake_spawn_run)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "spawn_run",
                "tenant_id": "tenant-1",
                "caller_run_id": "run-1",
                "target_agent_slug": "agent-a",
                "scope_subset": ["agents.execute"],
                "idempotency_key": "k-1",
            }
        },
    )

    assert out["context"]["action"] == "orchestration.spawn_run"
    assert out["context"]["errors"] == []
    assert out["context"]["result"]["spawned_run_ids"] == ["child-1"]
    assert captured["inputs"]["idempotency_key"] == "k-1"
    assert captured["dry_run"] is False


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
