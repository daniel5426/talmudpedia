import json

from artifacts.builtin.platform_sdk import handler


def test_respond_action_prefers_payload_message():
    state = {}
    context = {"inputs": {"action": "respond", "payload": {"message": "Hello"}}}
    result = handler.execute(state, {}, context)

    assert result["context"]["action"] == "respond"
    assert result["context"]["result"]["message"] == "Hello"
    assert result["context"]["errors"] == []


def test_default_action_fetch_catalog(monkeypatch):
    def fake_fetch(client, payload):
        return {
            "summary": {
                "rag": {"total": 1, "categories": {"source": 1}, "examples": {"source": ["s3_loader"]}, "fields": []},
                "agent": {"total": 1, "categories": {"action": 1}, "examples": {"action": ["tool"]}, "fields": []},
            }
        }

    monkeypatch.setattr(handler, "_fetch_catalog", fake_fetch)

    result = handler.execute({}, {}, {"inputs": {}})
    assert result["context"]["action"] == "fetch_catalog"
    assert result["context"]["result"]["summary"]["rag"]["total"] == 1


def test_execute_plan_dry_run(monkeypatch):
    captured = {}

    def fake_execute(client, steps, dry_run):
        captured["steps"] = steps
        captured["dry_run"] = dry_run
        return {"steps": steps}, []

    def fake_validate(client, steps):
        return {"valid": True, "issues": []}, []

    monkeypatch.setattr(handler, "_execute_plan", fake_execute)
    monkeypatch.setattr(handler, "_validate_plan", fake_validate)

    inputs = {
        "action": "execute_plan",
        "steps": [{"action": "deploy_agent", "payload": {"name": "Test", "slug": "test"}}],
        "dry_run": True,
    }
    result = handler.execute({}, {}, {"inputs": inputs})

    assert captured["dry_run"] is True
    assert captured["steps"] == inputs["steps"]
    assert result["context"]["dry_run"] is True


def test_json_text_input_coercion():
    text = json.dumps({"action": "respond", "message": "Ok"})
    state = {"messages": [{"role": "user", "content": text}]}
    result = handler.execute(state, {}, {})

    assert result["context"]["action"] == "respond"
    assert result["context"]["result"]["message"] == "Ok"


def test_input_resolution_priority():
    state = {
        "context": {"action": "respond", "payload": {"message": "from context"}},
        "state": {"last_agent_output": {"action": "respond", "payload": {"message": "from last"}}},
    }
    context = {"inputs": {"action": "respond", "payload": {"message": "from inputs"}}}
    result = handler.execute(state, {}, context)

    assert result["context"]["result"]["message"] == "from inputs"


def test_validate_plan_action(monkeypatch):
    def fake_validate(client, steps):
        return {"valid": False, "issues": [{"error": "bad"}]}, [{"error": "bad"}]

    monkeypatch.setattr(handler, "_validate_plan", fake_validate)
    result = handler.execute({}, {}, {"inputs": {"action": "validate_plan", "steps": [{"action": "deploy_agent"}]}})

    assert result["context"]["action"] == "validate_plan"
    assert result["context"]["errors"][0]["error"] == "bad"


def test_execute_plan_skips_on_validation_errors(monkeypatch):
    def fake_validate(client, steps):
        return {"valid": False, "issues": [{"error": "bad"}]}, [{"error": "bad"}]

    def fail_execute(*args, **kwargs):
        raise AssertionError("execute_plan should not run when validation fails")

    monkeypatch.setattr(handler, "_validate_plan", fake_validate)
    monkeypatch.setattr(handler, "_execute_plan", fail_execute)

    inputs = {"action": "execute_plan", "steps": [{"action": "deploy_agent"}]}
    result = handler.execute({}, {}, {"inputs": inputs})

    assert result["context"]["action"] == "execute_plan"
    assert result["context"]["errors"][0]["error"] == "bad"
    assert result["context"]["result"]["status"] == "validation_failed"
