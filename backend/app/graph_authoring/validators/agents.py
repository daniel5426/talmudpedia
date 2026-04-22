from __future__ import annotations

from difflib import get_close_matches
from typing import Any

from app.agent.executors.standard import register_standard_operators
from app.agent.registry import AgentOperatorRegistry
from app.graph_authoring.registry import get_agent_authoring_spec, normalize_agent_node_type
from app.graph_authoring.schema import required_config_fields
from app.graph_authoring.validators.base import build_authoring_issue


WRITE_REJECT_CODES = {"UNKNOWN_NODE_TYPE", "UNKNOWN_CONFIG_FIELD"}
INTERNAL_CONFIG_FIELDS: dict[str, set[str]] = {
    "router": {"route_table", "routes"},
    "judge": {"route_table", "outcomes"},
}


def critical_agent_write_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        issue
        for issue in issues
        if str(issue.get("severity") or "").lower() == "error"
        and str(issue.get("code") or "") in WRITE_REJECT_CODES
    ]


def collect_agent_authoring_issues(graph_definition: dict[str, Any]) -> list[dict[str, Any]]:
    register_standard_operators()
    operator_types = [spec.type for spec in AgentOperatorRegistry.list_operators()]
    issues: list[dict[str, Any]] = []
    nodes = graph_definition.get("nodes") if isinstance(graph_definition.get("nodes"), list) else []

    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip() or None
        raw_node_type = str(node.get("type") or "").strip()
        node_type = normalize_agent_node_type(raw_node_type)
        path_prefix = f"/nodes/{idx}"

        if not node_type:
            issues.append(
                build_authoring_issue(
                    code="UNKNOWN_NODE_TYPE",
                    message="Node type is required",
                    node_id=node_id,
                    path=f"{path_prefix}/type",
                    expected="Registered node type",
                    actual=raw_node_type,
                    repair_hint="Choose a node type returned by /agents/nodes/catalog.",
                )
            )
            continue

        if not node_type.startswith("artifact:") and AgentOperatorRegistry.get(node_type) is None:
            suggestions = get_close_matches(node_type, operator_types, n=5, cutoff=0.35) or None
            issues.append(
                build_authoring_issue(
                    code="UNKNOWN_NODE_TYPE",
                    message=f"Unknown node type '{raw_node_type or node_type}'",
                    node_id=node_id,
                    path=f"{path_prefix}/type",
                    expected="Registered node type",
                    actual=raw_node_type or node_type,
                    suggestions=suggestions,
                    suggested_value=suggestions[0] if suggestions else None,
                    repair_hint="Choose a node type returned by /agents/nodes/catalog.",
                )
            )
            continue

        spec = get_agent_authoring_spec(node_type)
        if spec is None:
            continue
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        properties = spec.config_schema.get("properties") if isinstance(spec.config_schema.get("properties"), dict) else {}
        allowed_fields = {str(key) for key in properties.keys()}
        allowed_fields.update(INTERNAL_CONFIG_FIELDS.get(node_type, set()))

        for key in config.keys():
            field_name = str(key or "").strip()
            if not field_name or not allowed_fields or field_name in allowed_fields:
                continue
            suggestions = get_close_matches(field_name, list(allowed_fields), n=5, cutoff=0.35) or None
            issues.append(
                build_authoring_issue(
                    code="UNKNOWN_CONFIG_FIELD",
                    message=f"Config field '{field_name}' is not valid for node type '{node_type}'",
                    node_id=node_id,
                    path=f"{path_prefix}/config/{field_name}",
                    expected=sorted(allowed_fields),
                    actual=config.get(key),
                    suggestions=suggestions,
                    suggested_value=suggestions[0] if suggestions else None,
                    repair_hint="Remove the field or rename it to a field returned by /agents/nodes/schema.",
                )
            )

        for field_name in required_config_fields(spec.config_schema):
            value = config.get(field_name)
            if _has_meaningful_value(value):
                continue
            issues.append(
                build_authoring_issue(
                    code="MISSING_REQUIRED_CONFIG",
                    message=f"Required config field '{field_name}' is missing for node type '{node_type}'",
                    node_id=node_id,
                    path=f"{path_prefix}/config/{field_name}",
                    expected="Non-empty value",
                    actual=value,
                    repair_hint="Fill this required field or remove the node until it is configured.",
                )
            )

    return issues


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True
