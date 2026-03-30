from __future__ import annotations

import json
from typing import Any


_ROOT_SKIP_KEYS = {
    "attachment_ids",
    "attachments",
    "context",
    "input_display_text",
    "input",
    "messages",
    "state",
    "thread_id",
}

_PROMPT_CONTEXT_KEYS = {
    "selected_agent_contract",
    "artifact_payload",
    "draft_snapshot",
    "platform_assets_create_input",
    "platform_assets_update_input",
}


class PromptSnapshotService:
    @staticmethod
    def serialize_message(message: Any) -> dict[str, Any]:
        if isinstance(message, dict):
            return dict(message)
        payload: dict[str, Any] = {
            "role": getattr(message, "type", None) or message.__class__.__name__,
            "content": getattr(message, "content", None),
        }
        tool_calls = getattr(message, "tool_calls", None)
        if isinstance(tool_calls, list) and tool_calls:
            payload["tool_calls"] = tool_calls
        name = getattr(message, "name", None)
        if name:
            payload["name"] = name
        additional_kwargs = getattr(message, "additional_kwargs", None)
        if isinstance(additional_kwargs, dict) and additional_kwargs:
            if additional_kwargs.get("reasoning_content"):
                payload["reasoning_content"] = additional_kwargs.get("reasoning_content")
            if additional_kwargs.get("citations"):
                payload["citations"] = additional_kwargs.get("citations")
            if additional_kwargs.get("server_tool_results"):
                payload["server_tool_results"] = additional_kwargs.get("server_tool_results")
        return payload

    @classmethod
    def build_from_langchain(
        cls,
        *,
        messages: list[Any] | None = None,
        system_prompt: str | None = None,
        tools: list[Any] | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "system_prompt": str(system_prompt or "").strip() or None,
            "messages": [cls.serialize_message(item) for item in (messages or [])],
            "tools": list(tools or []),
            "extra_context": dict(extra_context or {}) or None,
        }

    @classmethod
    def build_from_input_params(
        cls,
        *,
        input_params: dict[str, Any],
        runtime_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        messages = input_params.get("messages")
        normalized_messages = [dict(item) for item in messages] if isinstance(messages, list) else []
        raw_input = str(input_params.get("input") or "").strip()
        if raw_input:
            duplicate_in_messages = False
            for message in reversed(normalized_messages):
                if not isinstance(message, dict):
                    continue
                if str(message.get("role") or "").strip().lower() != "user":
                    continue
                if str(message.get("content") or "").strip() == raw_input:
                    duplicate_in_messages = True
                break
            if not duplicate_in_messages:
                normalized_messages.append({"role": "user", "content": raw_input})

        extra_context: dict[str, Any] = {}
        extra_system_parts: list[str] = []
        attachments = input_params.get("attachments")
        if attachments:
            extra_context["attachments"] = attachments
        for key, value in input_params.items():
            if key in _ROOT_SKIP_KEYS:
                continue
            extra_context[key] = value
        if isinstance(runtime_context, dict):
            for key in _PROMPT_CONTEXT_KEYS:
                if key in runtime_context:
                    extra_context[key] = runtime_context.get(key)
        if extra_context:
            extra_system_parts.append(
                "Additional prompt context:\n" + json.dumps(extra_context, ensure_ascii=False, sort_keys=True, default=str)
            )

        return {
            "system_prompt": "\n\n".join(extra_system_parts) if extra_system_parts else None,
            "messages": normalized_messages,
            "tools": [],
            "extra_context": extra_context or None,
        }
