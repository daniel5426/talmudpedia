import pytest

from app.agent.execution.adapter import StreamAdapter
from app.agent.execution.types import ExecutionMode
from app.agent.execution.stream_contract_v2 import normalize_filtered_event_to_v2
from app.agent.execution.tool_event_metadata import resolve_tool_event_metadata
from app.services.context_status_service import ContextStatusService


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


def test_ui_blocks_tool_metadata_and_completed_output_kind_are_preserved():
    metadata = resolve_tool_event_metadata(
        tool_slug="builtin-ui-blocks",
        tool_name="UI Blocks",
        input_data={"rows": [{"blocks": [{"kind": "note", "id": "n1", "span": 12, "title": "Note", "text": "ok"}]}]},
    )

    assert metadata["renderer_kind"] == "ui_blocks"

    event_name, stage, payload, diagnostics = normalize_filtered_event_to_v2(
        raw_event={
            "event": "on_tool_end",
            "name": "UI Blocks",
            "span_id": "call-ui-1",
            "data": {
                "tool_slug": "builtin-ui-blocks",
                "renderer_kind": "ui_blocks",
                "display_name": "UI Blocks",
                "output": {
                    "kind": "ui_blocks_bundle",
                    "contract_version": "v1",
                    "bundle": {
                        "rows": [
                            {
                                "blocks": [
                                    {"kind": "note", "id": "n1", "span": 12, "title": "Note", "text": "ok"}
                                ]
                            }
                        ]
                    },
                },
            },
        }
    )

    assert event_name == "tool.completed"
    assert stage == "tool"
    assert diagnostics == []
    assert payload["renderer_kind"] == "ui_blocks"
    assert payload["output_kind"] == "ui_blocks_bundle"


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


def test_normalize_filtered_event_to_v2_maps_tool_failed_to_terminal_tool_event():
    event_name, stage, payload, diagnostics = normalize_filtered_event_to_v2(
        raw_event={
            "event": "tool.failed",
            "name": "Architect Worker Spawn",
            "span_id": "call-err-1",
            "data": {
                "tool_slug": "architect-worker-spawn",
                "display_name": "Architect Worker Spawn",
                "error": "task.objective is required",
                "input": {"binding_ref": {"binding_type": "artifact_shared_draft", "binding_id": "x"}},
            },
        }
    )

    assert event_name == "tool.failed"
    assert stage == "tool"
    assert payload["tool"] == "Architect Worker Spawn"
    assert payload["tool_slug"] == "architect-worker-spawn"
    assert payload["error"] == "task.objective is required"
    assert diagnostics == [{"message": "task.objective is required"}]


def test_context_status_service_advances_inflight_status_from_tool_output():
    next_status, runtime_metadata = ContextStatusService.advance_for_event(
        existing_status={
            "model_id": "openai/gpt-5",
            "max_tokens": 1000,
            "max_tokens_source": "registry",
            "reserved_output_tokens": 100,
            "estimated_input_tokens": 200,
            "estimated_total_tokens": 300,
            "estimated_remaining_tokens": 700,
            "estimated_usage_ratio": 0.3,
            "near_limit": False,
            "compaction_recommended": False,
            "source": "estimated_pre_run",
        },
        existing_runtime_metadata=None,
        event_name="on_tool_end",
        data={"output": {"content": "x" * 80}},
    )

    assert next_status is not None
    assert runtime_metadata is not None
    assert next_status["source"] == "estimated_in_flight"
    assert next_status["estimated_input_tokens"] == 220
    assert next_status["estimated_total_tokens"] == 320
    assert runtime_metadata["inflight_added_input_tokens"] == 20
    assert runtime_metadata["last_context_event"] == "on_tool_end"


def test_normalize_filtered_event_to_v2_preserves_context_status_events():
    event_name, stage, payload, diagnostics = normalize_filtered_event_to_v2(
        raw_event={
            "event": "context.status",
            "data": {
                "context_status": {
                    "model_id": "openai/gpt-5",
                    "source": "estimated_in_flight",
                    "estimated_total_tokens": 320,
                }
            },
        }
    )

    assert event_name == "context.status"
    assert stage == "context"
    assert diagnostics == []
    assert payload["context_status"]["source"] == "estimated_in_flight"


@pytest.mark.asyncio
async def test_stream_adapter_keeps_tool_failed_and_emits_failed_reasoning_step():
    async def _stream():
        yield {
            "event": "tool.failed",
            "name": "Architect Worker Join",
            "span_id": "join-call-1",
            "data": {
                "tool_slug": "architect-worker-join",
                "error": "Orchestration group not found",
            },
            "visibility": "client_safe",
        }

    events = [item async for item in StreamAdapter.filter_stream(_stream(), ExecutionMode.PRODUCTION)]

    assert events[0]["event"] == "tool.failed"
    assert events[0]["data"]["error"] == "Orchestration group not found"
    assert events[1]["type"] == "reasoning"
    assert events[1]["data"]["status"] == "failed"
    assert events[1]["data"]["error"] == "Orchestration group not found"
