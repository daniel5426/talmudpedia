from uuid import uuid4

from app.agent.executors.tool import ToolNodeExecutor


def test_tool_executor_uses_last_agent_output_when_context_empty():
    executor = ToolNodeExecutor(uuid4(), None)
    state = {
        "context": {},
        "state": {
            "last_agent_output": {"action": "execute_plan", "steps": []}
        },
        "messages": [],
    }

    resolved = executor._resolve_input_data(state)
    assert resolved == {"action": "execute_plan", "steps": []}


def test_tool_executor_prefers_last_agent_output_when_configured():
    executor = ToolNodeExecutor(uuid4(), None)
    state = {
        "context": {"action": "fetch_catalog"},
        "state": {"last_agent_output": {"action": "execute_plan", "steps": [{"action": "noop"}]}},
        "messages": [],
    }
    resolved = executor._resolve_input_data(state, {"input_source": "last_agent_output"})
    assert resolved == {"action": "execute_plan", "steps": [{"action": "noop"}]}
