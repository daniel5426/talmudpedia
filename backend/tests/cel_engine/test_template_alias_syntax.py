from app.agent.cel_engine import evaluate_template


def test_evaluate_template_supports_at_alias_syntax():
    result = evaluate_template(
        "Hello @state.user_name from @workflow_input.text",
        {
            "state": {"user_name": "Ada"},
            "workflow_input": {"text": "chat"},
        },
    )

    assert result == "Hello Ada from chat"
