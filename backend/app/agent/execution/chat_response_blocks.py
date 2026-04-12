from __future__ import annotations

import json
import re
from typing import Any

from app.agent.execution.adapter import StreamAdapter
from app.agent.execution.stream_contract_v2 import normalize_filtered_event_to_v2
from app.agent.execution.types import ExecutionMode


ChatRenderBlock = dict[str, Any]


def _sort_blocks(blocks: list[ChatRenderBlock]) -> list[ChatRenderBlock]:
    return sorted(
        blocks,
        key=lambda block: (
            int(block.get("seq") or 0),
            str(block.get("ts") or ""),
            str(block.get("id") or ""),
        ),
    )


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _is_provider_structured_tool_delta_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    trimmed = value.strip()
    if not trimmed.startswith("{") or not trimmed.endswith("}"):
        return False
    normalized = trimmed.replace('"', "'")
    structured_types = (
        "tool_use",
        "input_json_delta",
        "tool_call",
        "tool_call_chunk",
        "server_tool_call",
        "server_tool_call_chunk",
    )
    return any(f"'type': '{item}'" in normalized for item in structured_types)


def strip_provider_structured_tool_delta_text(value: str) -> str:
    if not value:
        return ""

    patterns = [
        re.compile(
            r"\{['\"]id['\"]:\s*['\"][^'\"]+['\"],\s*['\"]caller['\"]:\s*\{[^{}]*\},\s*['\"]input['\"]:\s*\{[^{}]*\},\s*['\"]name['\"]:\s*['\"][^'\"]+['\"],\s*['\"]type['\"]:\s*['\"]tool_use['\"],\s*['\"]index['\"]:\s*\d+\}"
        ),
        re.compile(
            r"\{['\"]partial_json['\"]:\s*.*?['\"]type['\"]:\s*['\"]input_json_delta['\"],\s*['\"]index['\"]:\s*\d+\}"
        ),
    ]

    next_value = value
    for pattern in patterns:
        next_value = pattern.sub("", next_value)

    return re.sub(r"[ \t]{2,}", " ", next_value.replace("}{", "")).strip()


def _extract_structured_response_payload(value: Any) -> tuple[str, bool]:
    if value is None:
        return "", False

    if isinstance(value, dict):
        direct = value.get("message")
        if isinstance(direct, str) and direct.strip():
            return direct.strip(), True
        next_actions = value.get("next_actions")
        if isinstance(next_actions, list):
            for action in next_actions:
                if not isinstance(action, dict):
                    continue
                if str(action.get("action_type") or "").strip() != "respond_to_user":
                    continue
                payload = action.get("payload")
                if isinstance(payload, str) and payload.strip():
                    return payload.strip(), True
                if isinstance(payload, dict):
                    for key in ("message", "text", "content"):
                        nested = payload.get(key)
                        if isinstance(nested, str) and nested.strip():
                            return nested.strip(), True
        return "", False

    if not isinstance(value, str):
        return "", False

    trimmed = strip_provider_structured_tool_delta_text(value.strip())
    if not trimmed:
        return "", False
    raw = trimmed
    if trimmed.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", trimmed, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.IGNORECASE)

    try:
        parsed = json.loads(raw)
    except Exception:
        return "", False

    return _extract_structured_response_payload(parsed)


def extract_assistant_text_from_unknown(value: Any) -> str:
    if isinstance(value, str):
        trimmed = strip_provider_structured_tool_delta_text(value.strip())
        if not trimmed:
            return ""
        structured_text, is_structured = _extract_structured_response_payload(trimmed)
        return structured_text if is_structured else trimmed

    if value is None:
        return ""

    structured_text, is_structured = _extract_structured_response_payload(value)
    if is_structured:
        return structured_text

    if isinstance(value, dict):
        for key in ("message", "response", "text", "content"):
            nested = value.get(key)
            text = extract_assistant_text_from_unknown(nested)
            if text:
                return text
        for key in ("payload", "data", "result", "output"):
            nested = value.get(key)
            text = extract_assistant_text_from_unknown(nested)
            if text:
                return text

    try:
        return extract_assistant_text_from_unknown(json.dumps(value))
    except Exception:
        return ""


def _extract_assistant_text_with_source(value: Any) -> tuple[str, bool]:
    if isinstance(value, str):
        trimmed = strip_provider_structured_tool_delta_text(value.strip())
        if not trimmed:
            return "", False
        structured_text, is_structured = _extract_structured_response_payload(trimmed)
        return (structured_text if is_structured else trimmed, is_structured)
    if isinstance(value, dict):
        structured_text, is_structured = _extract_structured_response_payload(value)
        if is_structured:
            return structured_text, True
    return extract_assistant_text_from_unknown(value), False


def _create_assistant_text_block(
    *,
    block_id: str,
    text: str,
    run_id: str | None,
    seq: int,
    status: str = "complete",
    ts: str | None = None,
) -> ChatRenderBlock:
    return {
        "id": block_id,
        "kind": "assistant_text",
        "runId": run_id,
        "seq": seq,
        "status": status,
        "text": text,
        "ts": ts,
        "source": {"event": "assistant.text", "stage": "assistant"},
    }


def _create_approval_request_block(
    *,
    block_id: str,
    text: str,
    run_id: str | None,
    seq: int,
    ts: str | None = None,
) -> ChatRenderBlock:
    return {
        "id": block_id,
        "kind": "approval_request",
        "runId": run_id,
        "seq": seq,
        "status": "pending",
        "text": text,
        "ts": ts,
        "source": {"event": "approval.request", "stage": "assistant"},
    }


def _complete_streaming_assistant_blocks(blocks: list[ChatRenderBlock]) -> list[ChatRenderBlock]:
    next_blocks: list[ChatRenderBlock] = []
    for block in blocks:
        if block.get("kind") == "assistant_text" and block.get("status") == "streaming":
            next_block = dict(block)
            next_block["status"] = "complete"
            next_blocks.append(next_block)
            continue
        next_blocks.append(block)
    return next_blocks


def _tool_title(payload: dict[str, Any], tool_name: str) -> str:
    for key in ("display_name", "summary"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return tool_name or "Tool"


def apply_stream_v2_event_to_response_blocks(
    blocks: list[ChatRenderBlock],
    *,
    event: str,
    run_id: str | None,
    seq: int,
    ts: str | None,
    stage: str | None,
    payload: dict[str, Any] | None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[ChatRenderBlock]:
    payload = payload or {}
    diagnostics = diagnostics or []

    if event == "assistant.delta":
        content = strip_provider_structured_tool_delta_text(_to_text(payload.get("content")))
        if not content or _is_provider_structured_tool_delta_text(content):
            return blocks
        next_blocks = list(blocks)
        last_block = next_blocks[-1] if next_blocks else None
        if last_block and last_block.get("kind") == "assistant_text":
            updated = dict(last_block)
            updated["status"] = "streaming"
            updated["text"] = f"{_to_text(last_block.get('text'))}{content}"
            next_blocks[-1] = updated
            return next_blocks
        next_blocks.append(
            _create_assistant_text_block(
                block_id=f"assistant-text:{run_id or 'run'}:{seq}",
                text=content,
                run_id=run_id,
                seq=seq,
                status="streaming",
                ts=ts,
            )
        )
        return next_blocks

    if event == "tool.started":
        next_blocks = _complete_streaming_assistant_blocks(blocks)
        tool_name = _to_text(payload.get("tool")).strip() or "tool"
        tool_call_id = _to_text(payload.get("span_id")).strip() or None
        block_id = tool_call_id or f"tool:{seq}:{tool_name}"
        tool_block = {
            "id": block_id,
            "kind": "tool_call",
            "runId": run_id,
            "seq": seq,
            "status": "running",
            "ts": ts,
            "source": {"event": event, "stage": stage},
            "tool": {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "toolSlug": payload.get("tool_slug"),
                "action": payload.get("action"),
                "displayName": payload.get("display_name"),
                "summary": payload.get("summary"),
                "title": _tool_title(payload, tool_name),
                "detail": payload.get("message"),
                "path": None,
                "threadId": None,
                "isExploration": False,
                "input": payload.get("input"),
                "output": None,
            },
        }
        existing_index = next((idx for idx, item in enumerate(next_blocks) if item.get("kind") == "tool_call" and item.get("id") == block_id), -1)
        if existing_index >= 0:
            next_blocks[existing_index] = tool_block
            return next_blocks
        next_blocks.append(tool_block)
        return next_blocks

    if event in {"tool.completed", "tool.failed"}:
        next_blocks = _complete_streaming_assistant_blocks(blocks)
        tool_name = _to_text(payload.get("tool")).strip() or "tool"
        tool_call_id = _to_text(payload.get("span_id")).strip() or None
        existing_index = next((idx for idx, item in enumerate(next_blocks) if item.get("kind") == "tool_call" and item.get("id") == (tool_call_id or "")), -1)
        existing_tool = next_blocks[existing_index] if existing_index >= 0 else None
        status = "error" if event == "tool.failed" else "complete"
        tool_block = {
            "id": (existing_tool or {}).get("id") or tool_call_id or f"tool:{seq}:{tool_name}",
            "kind": "tool_call",
            "runId": run_id,
            "seq": int((existing_tool or {}).get("seq") or seq),
            "status": status,
            "ts": ts,
            "source": {"event": event, "stage": stage},
            "tool": {
                "toolCallId": tool_call_id or ((existing_tool or {}).get("tool") or {}).get("toolCallId"),
                "toolName": tool_name,
                "toolSlug": payload.get("tool_slug") or ((existing_tool or {}).get("tool") or {}).get("toolSlug"),
                "action": payload.get("action") or ((existing_tool or {}).get("tool") or {}).get("action"),
                "displayName": payload.get("display_name") or ((existing_tool or {}).get("tool") or {}).get("displayName"),
                "summary": payload.get("summary") or ((existing_tool or {}).get("tool") or {}).get("summary"),
                "title": _tool_title(payload, tool_name),
                "detail": payload.get("message") or payload.get("error") or ((existing_tool or {}).get("tool") or {}).get("detail"),
                "path": ((existing_tool or {}).get("tool") or {}).get("path"),
                "threadId": None,
                "isExploration": False,
                "input": ((existing_tool or {}).get("tool") or {}).get("input"),
                "output": payload.get("output") if event == "tool.completed" else {"error": payload.get("error")},
              },
        }
        if existing_index >= 0:
            next_blocks[existing_index] = tool_block
            return next_blocks
        next_blocks.append(tool_block)
        return next_blocks

    if event == "reasoning.update":
        step_id = _to_text(payload.get("step_id")).strip() or None
        if step_id and any(item.get("kind") == "tool_call" and ((item.get("tool") or {}).get("toolCallId") == step_id) for item in blocks):
            return blocks
        next_blocks = _complete_streaming_assistant_blocks(blocks)
        existing_index = next(
            (
                idx
                for idx, item in enumerate(next_blocks)
                if item.get("kind") == "reasoning_note" and step_id and item.get("stepId") == step_id
            ),
            -1,
        )
        raw_status = _to_text(payload.get("status")).strip().lower()
        status = "running" if raw_status == "active" else "pending" if raw_status == "pending" else "error" if raw_status == "failed" else "complete"
        reasoning_block = {
            "id": step_id or f"reasoning:{seq}:{_to_text(payload.get('step'))}",
            "kind": "reasoning_note",
            "runId": run_id,
            "seq": int(next_blocks[existing_index].get("seq") if existing_index >= 0 else seq),
            "status": status,
            "label": _to_text(payload.get("step")).strip() or "Reasoning",
            "description": payload.get("message"),
            "stepId": step_id,
            "ts": ts,
            "source": {"event": event, "stage": stage},
        }
        if existing_index >= 0:
            next_blocks[existing_index] = reasoning_block
            return next_blocks
        next_blocks.append(reasoning_block)
        return next_blocks

    if event in {"approval.request", "mcp.auth_required"}:
        next_blocks = _complete_streaming_assistant_blocks(blocks)
        next_blocks.append(
            _create_approval_request_block(
                block_id=f"approval:{run_id or 'run'}:{seq}",
                text=_to_text(payload.get("message")).strip() or "Approval required.",
                run_id=run_id,
                seq=seq,
                ts=ts,
            )
        )
        return next_blocks

    if event in {"run.failed", "runtime.error"}:
        next_blocks = _complete_streaming_assistant_blocks(blocks)
        error_text = _to_text(payload.get("error")).strip() or _to_text((diagnostics[0] if diagnostics else {}).get("message")).strip() or "Agent error"
        next_blocks.append(
            {
                "id": f"error:{run_id or 'run'}:{seq}",
                "kind": "error",
                "runId": run_id,
                "seq": seq,
                "status": "error",
                "text": error_text,
                "ts": ts,
                "source": {"event": event, "stage": stage},
            }
        )
        return next_blocks

    return blocks


def finalize_response_blocks(
    blocks: list[ChatRenderBlock],
    *,
    final_output: Any,
    run_id: str | None,
    fallback_seq: int | None = None,
) -> list[ChatRenderBlock]:
    next_blocks: list[ChatRenderBlock] = []
    for block in blocks:
        next_block = dict(block)
        if next_block.get("kind") == "tool_call" and next_block.get("status") == "running":
            next_block["status"] = "complete"
        elif next_block.get("kind") == "assistant_text" and next_block.get("status") in {"running", "streaming"}:
            next_block["status"] = "complete"
        elif next_block.get("kind") == "reasoning_note" and next_block.get("status") == "running":
            next_block["status"] = "complete"
        next_blocks.append(next_block)

    parsed_text, is_structured = _extract_assistant_text_with_source(final_output)
    if not parsed_text.strip():
        return _sort_blocks(next_blocks)

    assistant_indices = [idx for idx, block in enumerate(next_blocks) if block.get("kind") == "assistant_text"]
    concatenated_text = "".join(_to_text(next_blocks[idx].get("text")) for idx in assistant_indices).strip()
    if not assistant_indices:
        next_blocks.append(
            _create_assistant_text_block(
                block_id=f"assistant-text:{run_id or 'run'}:{fallback_seq or len(next_blocks) + 1}",
                text=parsed_text,
                run_id=run_id,
                seq=fallback_seq or len(next_blocks) + 1,
                status="complete",
            )
        )
        return _sort_blocks(next_blocks)

    if concatenated_text == parsed_text.strip():
        return _sort_blocks(next_blocks)

    if not is_structured:
        return _sort_blocks(next_blocks)

    if len(assistant_indices) == 1:
        idx = assistant_indices[0]
        replacement = dict(next_blocks[idx])
        replacement["text"] = parsed_text
        replacement["status"] = "complete"
        next_blocks[idx] = replacement
        return _sort_blocks(next_blocks)

    if any(block.get("kind") != "assistant_text" for block in next_blocks):
        return _sort_blocks(next_blocks)

    keep_index = assistant_indices[0]
    replacement = dict(next_blocks[keep_index])
    replacement["text"] = parsed_text
    replacement["status"] = "complete"
    next_blocks[keep_index] = replacement
    return _sort_blocks(
        [block for idx, block in enumerate(next_blocks) if block.get("kind") != "assistant_text" or idx == keep_index]
    )


def extract_assistant_text_from_blocks(blocks: list[ChatRenderBlock]) -> str:
    return "".join(_to_text(block.get("text")) for block in blocks if block.get("kind") == "assistant_text").strip()


def build_response_blocks_from_trace_events(
    *,
    raw_events: list[dict[str, Any]],
    run_id: str | None,
    final_output: Any,
    mode: ExecutionMode = ExecutionMode.PRODUCTION,
) -> list[ChatRenderBlock]:
    blocks: list[ChatRenderBlock] = []
    seq = 0
    for item in raw_events:
        event_name = _to_text(item.get("event")).strip()
        if not event_name:
            continue
        visibility = item.get("visibility")
        is_tool_lifecycle = event_name in StreamAdapter._TOOL_LIFECYCLE_EVENTS
        if mode == ExecutionMode.PRODUCTION and not (
            StreamAdapter._is_client_safe(visibility)
            or is_tool_lifecycle
            or event_name in StreamAdapter._PRODUCTION_LEGACY_ALLOW
        ):
            continue

        mapped_event, stage, payload, diagnostics = normalize_filtered_event_to_v2(
            raw_event={
                "event": event_name,
                "type": item.get("type"),
                "name": item.get("name"),
                "span_id": item.get("span_id"),
                "data": item.get("data") if isinstance(item.get("data"), dict) else {},
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            }
        )
        seq += 1
        blocks = apply_stream_v2_event_to_response_blocks(
            blocks,
            event=mapped_event,
            run_id=run_id,
            seq=seq,
            ts=_to_text(item.get("timestamp")).strip() or None,
            stage=stage,
            payload=payload,
            diagnostics=diagnostics,
        )

        reasoning = StreamAdapter._reasoning_event(
            event_type=event_name,
            event_name=_to_text(item.get("name")).strip() or None,
            step_id=_to_text(item.get("span_id")).strip() or None,
            data=item.get("data") if isinstance(item.get("data"), dict) else {},
        )
        if reasoning is None:
            continue
        mapped_event, stage, payload, diagnostics = normalize_filtered_event_to_v2(raw_event=reasoning)
        seq += 1
        blocks = apply_stream_v2_event_to_response_blocks(
            blocks,
            event=mapped_event,
            run_id=run_id,
            seq=seq,
            ts=_to_text(item.get("timestamp")).strip() or None,
            stage=stage,
            payload=payload,
            diagnostics=diagnostics,
        )

    return finalize_response_blocks(
        blocks,
        final_output=final_output,
        run_id=run_id,
        fallback_seq=seq + 1,
    )
