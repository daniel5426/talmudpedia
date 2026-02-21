from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent
from app.db.postgres.models.published_apps import PublishedApp
from app.db.postgres.models.registry import ToolRegistry

SUPPORTED_X_UI_KINDS = ("chart", "table", "stat")
X_UI_KEY = "x-ui"


def _enum_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _as_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _parse_uuid(value: Any) -> UUID | None:
    raw = _as_text(value)
    if not raw:
        return None
    try:
        return UUID(raw)
    except Exception:
        return None


def _extract_node_configs(node: dict[str, Any]) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    config = node.get("config")
    if isinstance(config, dict):
        configs.append(config)
    data = node.get("data")
    if isinstance(data, dict):
        nested_config = data.get("config")
        if isinstance(nested_config, dict):
            configs.append(nested_config)
    return configs


def _append_reference(target: list[str], seen: set[str], value: Any) -> None:
    text = _as_text(value)
    if not text or text in seen:
        return
    seen.add(text)
    target.append(text)


def _collect_tool_references(agent: Agent) -> list[str]:
    references: list[str] = []
    seen: set[str] = set()

    for value in list(agent.tools or []):
        _append_reference(references, seen, value)
    for value in list(agent.referenced_tool_ids or []):
        _append_reference(references, seen, value)

    graph_definition = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
    nodes = graph_definition.get("nodes")
    if not isinstance(nodes, list):
        return references

    for node in nodes:
        if not isinstance(node, dict):
            continue
        for config in _extract_node_configs(node):
            _append_reference(references, seen, config.get("tool_id"))
            _append_reference(references, seen, config.get("toolId"))
            tools = config.get("tools")
            if isinstance(tools, list):
                for tool in tools:
                    _append_reference(references, seen, tool)

    return references


def _extract_x_ui_value(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return None
    if X_UI_KEY in schema:
        return schema.get(X_UI_KEY)
    if "x_ui" in schema:
        return schema.get("x_ui")
    if "xUi" in schema:
        return schema.get("xUi")
    return None


def _normalize_ui_kind(value: Any) -> str | None:
    raw = _as_text(value).lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return None
    aliases = {
        "metric": "stat",
        "number": "stat",
        "grid": "table",
    }
    return aliases.get(raw, raw)


def _normalize_ui_hint(raw_hint: Any) -> dict[str, Any] | None:
    if isinstance(raw_hint, str):
        kind = _normalize_ui_kind(raw_hint)
        if not kind:
            return None
        return {"kind": kind}
    if isinstance(raw_hint, dict):
        hint = deepcopy(raw_hint)
        kind = _normalize_ui_kind(
            hint.get("kind") or hint.get("widget") or hint.get("type")
        )
        if kind:
            hint["kind"] = kind
        return hint
    return None


def _build_ui_hints(schema: dict[str, Any], input_schema: dict[str, Any], output_schema: dict[str, Any]) -> dict[str, Any] | None:
    tool_hint = _normalize_ui_hint(_extract_x_ui_value(schema))
    input_hint = _normalize_ui_hint(_extract_x_ui_value(input_schema))
    output_hint = _normalize_ui_hint(_extract_x_ui_value(output_schema))

    if tool_hint is None and input_hint is None and output_hint is None:
        return None

    kind = None
    for hint in (output_hint, input_hint, tool_hint):
        if isinstance(hint, dict) and isinstance(hint.get("kind"), str):
            kind = hint["kind"]
            break

    ui_hints: dict[str, Any] = {
        "optional": True,
        "schema_key": X_UI_KEY,
        "supported_kinds": list(SUPPORTED_X_UI_KINDS),
    }
    if kind:
        ui_hints["kind"] = kind
    if tool_hint is not None:
        ui_hints["tool"] = tool_hint
    if input_hint is not None:
        ui_hints["input"] = input_hint
    if output_hint is not None:
        ui_hints["output"] = output_hint
    return ui_hints


def _serialize_tool(tool: ToolRegistry, *, reference: str) -> dict[str, Any]:
    schema = tool.schema if isinstance(tool.schema, dict) else {}
    input_schema = deepcopy(schema.get("input") if isinstance(schema.get("input"), dict) else {})
    output_schema = deepcopy(schema.get("output") if isinstance(schema.get("output"), dict) else {})
    status = _enum_text(tool.status)

    readiness_issues: list[str] = []
    if not bool(tool.is_active):
        readiness_issues.append("inactive")
    if status.lower() != "published":
        readiness_issues.append("status_not_published")

    return {
        "id": str(tool.id),
        "reference": reference,
        "references": [reference],
        "name": str(tool.name or ""),
        "slug": str(tool.slug or ""),
        "description": str(tool.description or "") or None,
        "scope": "global" if tool.tenant_id is None else "tenant",
        "status": status,
        "implementation_type": _enum_text(tool.implementation_type),
        "is_active": bool(tool.is_active),
        "is_system": bool(tool.is_system),
        "runtime_readiness": {
            "ready": len(readiness_issues) == 0,
            "issues": readiness_issues,
        },
        "input_schema": input_schema,
        "output_schema": output_schema,
        "ui_hints": _build_ui_hints(schema, input_schema, output_schema),
    }


async def build_published_app_agent_integration_contract(
    *,
    db: AsyncSession,
    app: PublishedApp,
) -> dict[str, Any]:
    result = await db.execute(
        select(Agent).where(
            Agent.id == app.agent_id,
            Agent.tenant_id == app.tenant_id,
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise LookupError("Selected app agent was not found in tenant scope.")

    references = _collect_tool_references(agent)
    parsed_references: list[tuple[str, UUID]] = []
    unresolved_references: list[dict[str, str]] = []
    for ref in references:
        parsed = _parse_uuid(ref)
        if parsed is None:
            unresolved_references.append(
                {
                    "reference": ref,
                    "reason": "invalid_tool_reference",
                    "detail": "Reference is not a valid UUID.",
                }
            )
            continue
        parsed_references.append((ref, parsed))

    tool_rows: list[ToolRegistry] = []
    if parsed_references:
        unique_ids = list({tool_id for _, tool_id in parsed_references})
        tool_result = await db.execute(
            select(ToolRegistry).where(
                ToolRegistry.id.in_(unique_ids),
                or_(ToolRegistry.tenant_id == app.tenant_id, ToolRegistry.tenant_id.is_(None)),
            )
        )
        tool_rows = list(tool_result.scalars().all())
    tools_by_id = {str(tool.id): tool for tool in tool_rows}

    resolved_tools: list[dict[str, Any]] = []
    resolved_index: dict[str, int] = {}
    for raw_reference, tool_uuid in parsed_references:
        key = str(tool_uuid)
        tool = tools_by_id.get(key)
        if tool is None:
            unresolved_references.append(
                {
                    "reference": raw_reference,
                    "reason": "tool_not_found_or_not_accessible",
                    "detail": "Tool is missing or outside tenant/global scope.",
                }
            )
            continue

        if key in resolved_index:
            existing = resolved_tools[resolved_index[key]]
            refs = existing.get("references")
            if isinstance(refs, list) and raw_reference not in refs:
                refs.append(raw_reference)
            continue

        resolved_index[key] = len(resolved_tools)
        resolved_tools.append(_serialize_tool(tool, reference=raw_reference))

    graph_definition = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
    nodes = graph_definition.get("nodes") if isinstance(graph_definition.get("nodes"), list) else []
    edges = graph_definition.get("edges") if isinstance(graph_definition.get("edges"), list) else []

    return {
        "app_id": str(app.id),
        "agent_id": str(app.agent_id),
        "agent": {
            "id": str(agent.id),
            "name": str(agent.name or ""),
            "slug": str(agent.slug or ""),
            "description": str(agent.description or "") or None,
            "status": _enum_text(agent.status),
            "is_active": bool(agent.is_active),
            "version": int(agent.version or 1),
            "graph_summary": {
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        },
        "tool_reference_count": len(references),
        "resolved_tool_count": len(resolved_tools),
        "tools": resolved_tools,
        "unresolved_tool_references": unresolved_references,
        "ui_hint_standard": {
            "optional": True,
            "schema_key": X_UI_KEY,
            "supported_kinds": list(SUPPORTED_X_UI_KINDS),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
