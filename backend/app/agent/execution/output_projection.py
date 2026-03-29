from __future__ import annotations

from typing import Any


def extract_latest_assistant_text(output_result: dict[str, Any] | None) -> str | None:
    if not isinstance(output_result, dict):
        return None

    messages = output_result.get("messages")
    if isinstance(messages, list):
        # Runtime state usually carries full conversation history.
        # Persist only the latest assistant-visible text, not the workflow return value.
        last_assistant: str | None = None
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or msg.get("type") or "").strip().lower()
            content = msg.get("content")
            if role in {"assistant", "ai"} and isinstance(content, str):
                text = content.strip()
                if text:
                    last_assistant = text
        if last_assistant:
            return last_assistant

    state = output_result.get("state")
    if isinstance(state, dict):
        last_output = state.get("last_agent_output")
        if isinstance(last_output, str) and last_output.strip():
            return last_output.strip()

    return None


def extract_assistant_output_text(
    output_result: dict[str, Any] | None,
    *,
    allow_final_output_fallback: bool = False,
) -> str | None:
    assistant_text = extract_latest_assistant_text(output_result)
    if assistant_text:
        return assistant_text

    if allow_final_output_fallback and isinstance(output_result, dict):
        final_output = output_result.get("final_output")
        if isinstance(final_output, str) and final_output.strip():
            return final_output.strip()

    return None
