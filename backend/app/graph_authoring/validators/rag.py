from __future__ import annotations

from difflib import get_close_matches
from typing import Any

from app.graph_authoring.registry import get_rag_authoring_spec
from app.graph_authoring.schema import required_config_fields
from app.graph_authoring.validators.base import build_authoring_issue
from app.rag.pipeline.registry import OperatorRegistry


WRITE_REJECT_CODES = {"UNKNOWN_OPERATOR", "UNKNOWN_CONFIG_FIELD"}


def critical_rag_write_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        issue
        for issue in issues
        if str(issue.get("severity") or "").lower() == "error"
        and str(issue.get("code") or "") in WRITE_REJECT_CODES
    ]


def collect_rag_authoring_issues(
    graph_definition: dict[str, Any],
    *,
    organization_id: str | None = None,
    registry: OperatorRegistry | None = None,
) -> list[dict[str, Any]]:
    resolved_registry = registry or OperatorRegistry.get_instance()
    operator_ids = [spec.operator_id for spec in resolved_registry.list_all(organization_id)]
    issues: list[dict[str, Any]] = []
    nodes = graph_definition.get("nodes") if isinstance(graph_definition.get("nodes"), list) else []

    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip() or None
        operator_id = str(node.get("operator") or "").strip()
        path_prefix = f"/nodes/{idx}"
        spec = get_rag_authoring_spec(operator_id, organization_id=organization_id, registry=resolved_registry)
        if spec is None:
            suggestions = get_close_matches(operator_id, operator_ids, n=5, cutoff=0.35) or None
            issues.append(
                build_authoring_issue(
                    code="UNKNOWN_OPERATOR",
                    message=f"Unknown pipeline operator '{operator_id}'",
                    node_id=node_id,
                    path=f"{path_prefix}/operator",
                    expected="Registered pipeline operator",
                    actual=operator_id,
                    suggestions=suggestions,
                    suggested_value=suggestions[0] if suggestions else None,
                    repair_hint="Choose an operator returned by /admin/pipelines/operators/schema.",
                )
            )
            continue

        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        properties = spec.config_schema.get("properties") if isinstance(spec.config_schema.get("properties"), dict) else {}
        allowed_fields = {str(key) for key in properties.keys()}

        for key in config.keys():
            field_name = str(key or "").strip()
            if not field_name or not allowed_fields or field_name in allowed_fields:
                continue
            suggestions = get_close_matches(field_name, list(allowed_fields), n=5, cutoff=0.35) or None
            issues.append(
                build_authoring_issue(
                    code="UNKNOWN_CONFIG_FIELD",
                    message=f"Config field '{field_name}' is not valid for operator '{operator_id}'",
                    node_id=node_id,
                    path=f"{path_prefix}/config/{field_name}",
                    expected=sorted(allowed_fields),
                    actual=config.get(key),
                    suggestions=suggestions,
                    suggested_value=suggestions[0] if suggestions else None,
                    repair_hint="Remove the field or rename it to a field returned by /admin/pipelines/operators/schema.",
                )
            )

        for field_name in required_config_fields(spec.config_schema):
            value = config.get(field_name)
            if _has_meaningful_value(value):
                continue
            issues.append(
                build_authoring_issue(
                    code="MISSING_REQUIRED_CONFIG",
                    message=f"Required config field '{field_name}' is missing for operator '{operator_id}'",
                    node_id=node_id,
                    path=f"{path_prefix}/config/{field_name}",
                    expected="Non-empty value",
                    actual=value,
                    repair_hint="Fill this required field or remove the operator until it is configured.",
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
