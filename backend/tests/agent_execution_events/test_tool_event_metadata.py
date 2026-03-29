import pytest

from app.agent.execution.adapter import StreamAdapter
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.stream_contract_v2 import normalize_filtered_event_to_v2
from app.agent.execution.types import ExecutionMode
from app.agent.execution.tool_event_metadata import resolve_tool_event_metadata
from app.services.context_window_service import ContextWindowService
from app.services.run_invocation_service import RunInvocationService


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


def test_context_window_service_estimates_prompt_input_from_model_visible_material_only():
    tokens = ContextWindowService.estimate_input_tokens_from_input_params(
        input_params={
            "input": "Update the artifact",
            "messages": [{"role": "user", "content": "Update the artifact"}],
            "attachments": [{"name": "contract.json", "content": "hello"}],
            "metadata": {"ignored": "still model-visible"},
        },
        runtime_context={
            "artifact_payload": {"display_name": "Draft artifact"},
            "draft_snapshot": {"source_files": [{"path": "main.py", "content": "x" * 4000}]},
            "context_window": {"input_tokens": 999999},
            "resource_policy_snapshot": {"large": "x" * 5000},
        },
    )

    assert tokens > 1000
    assert tokens < 1100


def test_normalize_filtered_event_to_v2_preserves_context_window_events():
    event_name, stage, payload, diagnostics = normalize_filtered_event_to_v2(
        raw_event={
            "event": "context_window.updated",
            "data": {
                "context_window": {
                    "model_id": "openai/gpt-5",
                    "source": "estimated",
                    "input_tokens": 320,
                }
            },
        }
    )

    assert event_name == "context_window.updated"
    assert stage == "context"
    assert diagnostics == []
    assert payload["context_window"]["source"] == "estimated"


def test_normalize_filtered_event_to_v2_preserves_artifact_draft_updated_events():
    event_name, stage, payload, diagnostics = normalize_filtered_event_to_v2(
        raw_event={
            "event": "artifact.draft.updated",
            "data": {
                "session_id": "session-1",
                "shared_draft_id": "draft-1",
                "tool_slug": "artifact-coding-replace-file",
                "summary": "Updated file.",
                "changed_fields": ["source_files"],
            },
        }
    )

    assert event_name == "artifact.draft.updated"
    assert stage == "artifact"
    assert diagnostics == []
    assert payload["session_id"] == "session-1"
    assert payload["tool_slug"] == "artifact-coding-replace-file"


def test_extract_usage_candidate_reads_nested_node_end_usage_payload():
    usage, usage_source = AgentExecutorService._extract_usage_candidate(
        event=type(
            "Event",
            (),
            {
                "data": {
                    "output": {
                        "usage": {
                            "input_tokens": 120,
                            "output_tokens": 45,
                            "total_tokens": 165,
                        },
                        "usage_source": "provider_reported",
                    }
                }
            },
        )()
    )

    assert usage is not None
    assert usage.input_tokens == 120
    assert usage.output_tokens == 45
    assert usage.total_tokens == 165
    assert usage_source == "exact"


def test_invocation_payload_prefers_prompt_estimate_for_context_window_over_exact_usage():
    payload = RunInvocationService.build_invocation_payload(
        model_id="openai/gpt-5",
        resolved_provider="google",
        resolved_provider_model_id="gemini-2.5-pro",
        node_id="node-1",
        node_name="Artifact Coding Agent",
        node_type="agent",
        max_context_tokens=1_000_000,
        max_context_tokens_source="resolved_execution",
        estimated_input_tokens=11_973,
        exact_usage_payload={
            "input_tokens": 870,
            "output_tokens": 27,
            "total_tokens": 897,
        },
        estimated_output_tokens=27,
    )

    assert payload["usage"]["source"] == "exact"
    assert payload["usage"]["input_tokens"] == 870
    assert payload["context_window"]["source"] == "estimated"
    assert payload["context_window"]["input_tokens"] == 11_973


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
