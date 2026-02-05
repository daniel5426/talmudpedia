from artifacts.builtin.platform_sdk import handler as platform_sdk_handler


def test_validate_plan_action_errors(monkeypatch):
    def fake_validate(client, steps):
        return {"valid": False, "issues": [{"error": "invalid_graph"}]}, [{"error": "invalid_graph"}]

    monkeypatch.setattr(platform_sdk_handler, "_validate_plan", fake_validate)
    result = platform_sdk_handler.execute(
        state={},
        config={},
        context={"inputs": {"action": "validate_plan", "steps": [{"action": "deploy_agent"}]}},
    )

    assert result["context"]["action"] == "validate_plan"
    assert result["context"]["errors"][0]["error"] == "invalid_graph"


def test_execute_plan_skips_on_validation_fail(monkeypatch):
    def fake_validate(client, steps):
        return {"valid": False, "issues": [{"error": "invalid_graph"}]}, [{"error": "invalid_graph"}]

    def fail_execute(*args, **kwargs):
        raise AssertionError("execute_plan should not run when validation fails")

    monkeypatch.setattr(platform_sdk_handler, "_validate_plan", fake_validate)
    monkeypatch.setattr(platform_sdk_handler, "_execute_plan", fail_execute)

    result = platform_sdk_handler.execute(
        state={},
        config={},
        context={"inputs": {"action": "execute_plan", "steps": [{"action": "deploy_agent"}]}},
    )

    assert result["context"]["result"]["status"] == "validation_failed"
    assert result["context"]["errors"][0]["error"] == "invalid_graph"


def test_execute_plan_runs_when_validation_passes(monkeypatch):
    def fake_validate(client, steps):
        return {"valid": True, "issues": []}, []

    executed = {"called": False}

    def fake_execute(client, steps, dry_run):
        executed["called"] = True
        return {"steps": []}, []

    monkeypatch.setattr(platform_sdk_handler, "_validate_plan", fake_validate)
    monkeypatch.setattr(platform_sdk_handler, "_execute_plan", fake_execute)

    result = platform_sdk_handler.execute(
        state={},
        config={},
        context={"inputs": {"action": "execute_plan", "steps": []}},
    )

    assert executed["called"] is True
    assert result["context"]["action"] == "execute_plan"
