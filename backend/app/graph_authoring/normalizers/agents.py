from __future__ import annotations

from typing import Any

from app.agent.graph.contracts import normalize_end_output_config, normalize_set_state_assignment, normalize_value_ref
from app.agent.graph.schema import AgentGraph
from app.graph_authoring.normalizers.base import apply_schema_defaults
from app.graph_authoring.registry import get_agent_authoring_spec, normalize_agent_node_type


def normalize_agent_graph_definition(graph_definition: dict[str, Any]) -> dict[str, Any]:
    payload = dict(graph_definition or {})
    normalized_nodes: list[dict[str, Any]] = []
    for raw_node in payload.get("nodes") or []:
        if not isinstance(raw_node, dict):
            normalized_nodes.append(raw_node)
            continue
        node = dict(raw_node)
        node_type = normalize_agent_node_type(node.get("type"))
        node["type"] = node_type
        config = node.get("config")
        if not isinstance(config, dict):
            nested_data = node.get("data") if isinstance(node.get("data"), dict) else {}
            config = nested_data.get("config") if isinstance(nested_data.get("config"), dict) else {}
        node["config"] = _normalize_agent_node_config(node_type, config if isinstance(config, dict) else {})
        normalized_nodes.append(node)
    payload["nodes"] = normalized_nodes
    graph = AgentGraph(**payload)
    return graph.model_dump()


def _normalize_agent_node_config(node_type: str, config: dict[str, Any]) -> dict[str, Any]:
    spec = get_agent_authoring_spec(node_type)
    normalized = apply_schema_defaults(spec.config_schema if spec else None, config)

    if node_type == "classify" and isinstance(normalized.get("input_source"), dict):
        normalized["input_source"] = normalize_value_ref(normalized.get("input_source"))

    if node_type == "set_state":
        assignments = normalized.get("assignments")
        normalized["assignments"] = [
            assignment
            for assignment in (
                normalize_set_state_assignment(item)
                for item in (assignments if isinstance(assignments, list) else [])
            )
            if str(assignment.get("key") or "").strip()
        ]

    if node_type == "end":
        normalized = normalize_end_output_config(normalized)

    if node_type == "router":
        route_rows = _normalize_route_table_rows(normalized.get("route_table") or normalized.get("routes"))
        if route_rows:
            normalized["route_table"] = route_rows
            normalized["routes"] = [{"name": row["name"], "match": row["match"]} for row in route_rows]

    if node_type == "judge":
        route_rows = _normalize_route_table_rows(normalized.get("route_table") or normalized.get("outcomes"))
        if route_rows:
            normalized["route_table"] = route_rows
            normalized["outcomes"] = [row["name"] for row in route_rows if str(row.get("name") or "").strip()]
        else:
            pass_outcome = str(normalized.get("pass_outcome") or "pass").strip() or "pass"
            fail_outcome = str(normalized.get("fail_outcome") or "fail").strip() or "fail"
            normalized["pass_outcome"] = pass_outcome
            normalized["fail_outcome"] = fail_outcome
            normalized["outcomes"] = _unique_strings([pass_outcome, fail_outcome])

    return normalized


def _normalize_route_table_rows(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    used: set[str] = set()
    normalized: list[dict[str, str]] = []
    for idx, item in enumerate(value):
        row = dict(item) if isinstance(item, dict) else {}
        raw_name = item if isinstance(item, str) else row.get("name")
        base = str(raw_name or "").strip() or f"route_{idx}"
        name = base
        suffix = 1
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1
        used.add(name)
        match = row.get("match") if isinstance(item, dict) and "match" in row else name
        normalized.append({"name": name, "match": str(match or "").strip()})
    return normalized


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized
