from __future__ import annotations

import json
from typing import Any


def _walk_values(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_values(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _walk_values(item)
        return
    if value is None:
        return
    yield str(value)


def contains_token(payload: Any, token: str) -> bool:
    wanted = str(token)
    for chunk in _walk_values(payload):
        if wanted in chunk:
            return True
    return False


def extract_first_json_object(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()

    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def extract_assistant_text(run_status_payload: dict[str, Any]) -> str:
    result = run_status_payload.get("result")
    if not isinstance(result, dict):
        return ""

    output = result.get("output")
    if isinstance(output, dict):
        text = output.get("text")
        if isinstance(text, str) and text.strip():
            return text

    messages = result.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, dict) and str(message.get("role", "")).lower() in {"assistant", "ai"}:
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content

    alt = result.get("last_agent_output")
    if isinstance(alt, str):
        return alt

    return ""
