from app.agent.execution.chat_response_blocks import (
    build_response_blocks_from_trace_events,
    extract_assistant_text_from_blocks,
)
from app.agent.execution.types import ExecutionMode


def test_build_response_blocks_from_trace_events_strips_provider_tool_delta_text():
    blocks = build_response_blocks_from_trace_events(
        raw_events=[
            {
                "event": "token",
                "visibility": "client_safe",
                "data": {
                    "content": "{'id': 'toolu_123', 'caller': {'type': 'direct'}, 'input': {}, 'name': 'mcp_line_list_projects', 'type': 'tool_use', 'index': 0}",
                },
            },
            {
                "event": "token",
                "visibility": "client_safe",
                "data": {
                    "content": "## Summary\n\n- Clean output",
                },
            },
        ],
        run_id="run-1",
        final_output=None,
        mode=ExecutionMode.PRODUCTION,
    )

    assert extract_assistant_text_from_blocks(blocks) == "## Summary\n\n- Clean output"
    assert [block["kind"] for block in blocks] == ["assistant_text"]


def test_build_response_blocks_from_trace_events_preserves_delta_whitespace_between_chunks():
    blocks = build_response_blocks_from_trace_events(
        raw_events=[
            {
                "event": "token",
                "visibility": "client_safe",
                "data": {"content": "Hello "},
            },
            {
                "event": "token",
                "visibility": "client_safe",
                "data": {"content": "**world**"},
            },
            {
                "event": "token",
                "visibility": "client_safe",
                "data": {"content": "\n\n- item"},
            },
        ],
        run_id="run-1",
        final_output=None,
        mode=ExecutionMode.PRODUCTION,
    )

    assert extract_assistant_text_from_blocks(blocks) == "Hello **world**\n\n- item"


def test_build_response_blocks_from_trace_events_keeps_tool_and_reasoning_timeline():
    blocks = build_response_blocks_from_trace_events(
        raw_events=[
            {
                "event": "on_tool_start",
                "name": "platform sdk",
                "span_id": "call-1",
                "visibility": "internal",
                "data": {
                    "input": {"topic": "Shabbat"},
                    "display_name": "List sources",
                    "summary": "List sources",
                },
            },
            {
                "event": "on_tool_end",
                "name": "platform sdk",
                "span_id": "call-1",
                "visibility": "internal",
                "data": {
                    "output": {"items": []},
                    "display_name": "List sources",
                    "summary": "List sources",
                },
            },
        ],
        run_id="run-1",
        final_output={"message": "Done."},
        mode=ExecutionMode.PRODUCTION,
    )

    assert [block["kind"] for block in blocks] == ["tool_call", "assistant_text"]
    assert blocks[0]["status"] == "complete"
    assert blocks[1]["text"] == "Done."


def test_build_response_blocks_from_trace_events_preserves_structured_markdown_final_output():
    blocks = build_response_blocks_from_trace_events(
        raw_events=[],
        run_id="run-1",
        final_output={"message": "## Title\n\n- item one\n- item two"},
        mode=ExecutionMode.PRODUCTION,
    )

    assert blocks == [
        {
            "id": "assistant-text:run-1:1",
            "kind": "assistant_text",
            "runId": "run-1",
            "seq": 1,
            "status": "complete",
            "text": "## Title\n\n- item one\n- item two",
            "ts": None,
            "source": {"event": "assistant.text", "stage": "assistant"},
        }
    ]


def test_build_response_blocks_from_trace_events_keeps_streamed_markdown_when_final_output_is_flatter():
    blocks = build_response_blocks_from_trace_events(
        raw_events=[
            {
                "event": "token",
                "visibility": "client_safe",
                "data": {"content": "## Summary\n\n- First item\n- Second item"},
            }
        ],
        run_id="run-1",
        final_output="## Summary - First item - Second item",
        mode=ExecutionMode.PRODUCTION,
    )

    assert extract_assistant_text_from_blocks(blocks) == "## Summary\n\n- First item\n- Second item"


def test_build_response_blocks_from_trace_events_emits_explicit_ui_blocks_block():
    blocks = build_response_blocks_from_trace_events(
        raw_events=[
            {
                "event": "on_tool_start",
                "name": "ui blocks",
                "span_id": "ui-call-1",
                "visibility": "internal",
                "data": {
                    "tool_slug": "builtin-ui-blocks",
                    "renderer_kind": "ui_blocks",
                },
            },
            {
                "event": "on_tool_end",
                "name": "ui blocks",
                "span_id": "ui-call-1",
                "visibility": "internal",
                "data": {
                    "tool_slug": "builtin-ui-blocks",
                    "renderer_kind": "ui_blocks",
                    "output": {
                        "kind": "ui_blocks_bundle",
                        "contract_version": "v1",
                        "bundle": {
                            "title": "Overview",
                            "rows": [
                                {
                                    "blocks": [
                                        {
                                            "id": "kpi-1",
                                            "kind": "kpi",
                                            "title": "Users",
                                            "value": "42",
                                            "span": 12,
                                        }
                                    ]
                                }
                            ],
                        },
                    },
                },
            },
        ],
        run_id="run-1",
        final_output={"message": "Done."},
        mode=ExecutionMode.PRODUCTION,
    )

    ui_block = next(block for block in blocks if block["kind"] == "ui_blocks")
    assistant_block = next(block for block in blocks if block["kind"] == "assistant_text")

    assert ui_block["status"] == "complete"
    assert ui_block["bundle"]["title"] == "Overview"
    assert ui_block["toolCallId"] == "ui-call-1"
    assert assistant_block["text"] == "Done."
