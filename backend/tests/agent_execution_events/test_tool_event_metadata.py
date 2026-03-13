from app.agent.execution.stream_contract_v2 import normalize_filtered_event_to_v2
from app.agent.execution.tool_event_metadata import resolve_tool_event_metadata


def test_resolve_tool_event_metadata_uses_platform_action_summary():
    metadata = resolve_tool_event_metadata(
        tool_slug="platform-agents",
        tool_name="platform sdk",
        input_data={"action": "agents.nodes.validate"},
    )

    assert metadata["tool_slug"] == "platform-agents"
    assert metadata["action"] == "agents.nodes.validate"
    assert metadata["summary"] == "Validate persisted agent graph by id with compiler and runtime reference checks."
    assert metadata["display_name"] == metadata["summary"]


def test_normalize_filtered_event_to_v2_preserves_tool_display_metadata():
    event_name, stage, payload, diagnostics = normalize_filtered_event_to_v2(
        raw_event={
            "event": "on_tool_start",
            "name": "platform sdk",
            "span_id": "call-1",
            "data": {
                "input": {"action": "agents.nodes.validate"},
                "tool_slug": "platform-agents",
                "action": "agents.nodes.validate",
                "display_name": "Validate agent graph",
                "summary": "Validate agent graph",
            },
        }
    )

    assert event_name == "tool.started"
    assert stage == "tool"
    assert diagnostics == []
    assert payload["tool"] == "platform sdk"
    assert payload["tool_slug"] == "platform-agents"
    assert payload["action"] == "agents.nodes.validate"
    assert payload["display_name"] == "Validate agent graph"
    assert payload["summary"] == "Validate agent graph"


def test_normalize_filtered_event_to_v2_keeps_generic_error_non_terminal():
    event_name, stage, payload, diagnostics = normalize_filtered_event_to_v2(
        raw_event={
            "event": "error",
            "data": {
                "error": "Action 'agents.tools.list' requires bearer token; missing caller auth context",
            },
        }
    )

    assert event_name == "runtime.error"
    assert stage == "system"
    assert payload["error"] == "Action 'agents.tools.list' requires bearer token; missing caller auth context"
    assert diagnostics == [
        {"message": "Action 'agents.tools.list' requires bearer token; missing caller auth context"}
    ]
