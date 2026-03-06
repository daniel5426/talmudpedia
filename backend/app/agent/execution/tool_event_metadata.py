from __future__ import annotations

from typing import Any

from app.services.platform_architect_contracts import PLATFORM_ARCHITECT_DOMAIN_TOOLS


def resolve_tool_event_metadata(
    *,
    tool_slug: str | None,
    tool_name: str,
    input_data: Any = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    normalized_tool_slug = str(tool_slug or "").strip()
    if normalized_tool_slug:
        metadata["tool_slug"] = normalized_tool_slug

    action = None
    if isinstance(input_data, dict):
        raw_action = input_data.get("action")
        if raw_action is not None:
            action = str(raw_action).strip()
    if action:
        metadata["action"] = action

    contract = (
        PLATFORM_ARCHITECT_DOMAIN_TOOLS.get(normalized_tool_slug, {})
        .get("actions", {})
        .get(action or "", {})
        .get("contract", {})
    )
    summary = str(contract.get("summary") or "").strip()
    if summary:
        metadata["summary"] = summary
        metadata["display_name"] = summary

    if not metadata.get("display_name"):
        metadata["display_name"] = str(tool_name or normalized_tool_slug or "Tool").strip()

    return metadata
