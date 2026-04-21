from __future__ import annotations

from typing import Any

from app.services.platform_architect_contracts import PLATFORM_ARCHITECT_DOMAIN_TOOLS
from app.services.ui_blocks import (
    UI_BLOCKS_RENDERER_KIND,
    UI_BLOCKS_BUILTIN_KEY,
)


def resolve_tool_event_metadata(
    *,
    builtin_key: str | None,
    tool_name: str,
    input_data: Any = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    normalized_builtin_key = str(builtin_key or "").strip()
    if normalized_builtin_key:
        metadata["builtin_key"] = normalized_builtin_key
        if normalized_builtin_key == UI_BLOCKS_BUILTIN_KEY:
            metadata["renderer_kind"] = UI_BLOCKS_RENDERER_KIND

    action = None
    if isinstance(input_data, dict):
        raw_action = input_data.get("action")
        if raw_action is not None:
            action = str(raw_action).strip()
    if action:
        metadata["action"] = action

    contract = (
        PLATFORM_ARCHITECT_DOMAIN_TOOLS.get(normalized_builtin_key, {})
        .get("actions", {})
        .get(action or "", {})
        .get("contract", {})
    )
    summary = str(contract.get("summary") or "").strip()
    if summary:
        metadata["summary"] = summary
        metadata["display_name"] = summary

    if not metadata.get("display_name"):
        metadata["display_name"] = str(tool_name or normalized_builtin_key or "Tool").strip()

    return metadata
