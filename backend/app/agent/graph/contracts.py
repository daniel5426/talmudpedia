from __future__ import annotations

import copy
import re
from typing import Any, Callable

import jsonschema

from app.agent.graph.ir import GRAPH_SPEC_V1, GRAPH_SPEC_V3, GRAPH_SPEC_V4


STATE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUPPORTED_VALUE_TYPES = {"string", "number", "boolean", "object", "list", "unknown"}


def normalize_value_type(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    if normalized == "array":
        normalized = "list"
    return normalized if normalized in SUPPORTED_VALUE_TYPES else "unknown"


def infer_runtime_value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "unknown"
    return "unknown"


def schema_to_value_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        non_null = [item for item in schema_type if item != "null"]
        schema_type = non_null[0] if len(non_null) == 1 else None
    if schema_type == "array":
        return "list"
    if schema_type in {"string", "number", "boolean", "object"}:
        return str(schema_type)
    if isinstance(schema.get("properties"), dict):
        return "object"
    if isinstance(schema.get("items"), dict):
        return "list"
    return "unknown"


def contract_fields_from_schema(
    schema: Any,
    *,
    fallback_key: str = "result",
    labels_by_key: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(schema, dict):
        return []

    labels = labels_by_key or {}
    schema_type = schema_to_value_type(schema)
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else None

    if schema_type == "object" and properties:
        fields: list[dict[str, Any]] = []
        for key, prop_schema in properties.items():
            normalized_key = str(key or "").strip()
            if not normalized_key:
                continue
            prop_dict = prop_schema if isinstance(prop_schema, dict) else {}
            fields.append(
                {
                    "key": normalized_key,
                    "type": schema_to_value_type(prop_dict),
                    "label": str(labels.get(normalized_key) or prop_dict.get("title") or normalized_key).strip(),
                }
            )
        if fields:
            return fields

    if not fallback_key:
        return []

    normalized_fallback = str(fallback_key).strip()
    if not normalized_fallback:
        return []
    return [
        {
            "key": normalized_fallback,
            "type": schema_type,
            "label": str(labels.get(normalized_fallback) or normalized_fallback).strip(),
        }
    ]


def value_types_compatible(expected: Any, actual: Any) -> bool:
    expected_type = normalize_value_type(expected)
    actual_type = normalize_value_type(actual)
    if expected_type == "unknown" or actual_type == "unknown":
        return True
    return expected_type == actual_type


def normalize_semantic_type(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def semantic_types_compatible(expected: Any, actual: Any) -> bool:
    expected_semantic = normalize_semantic_type(expected)
    actual_semantic = normalize_semantic_type(actual)
    if not expected_semantic or not actual_semantic:
        return True
    return expected_semantic == actual_semantic


def normalize_value_ref_namespace(value: Any) -> str:
    namespace = str(value or "").strip().lower()
    if namespace in {"node_output", "node_outputs", "upstream"}:
        return "node_output"
    if namespace == "workflow_input":
        return "workflow_input"
    if namespace == "state":
        return "state"
    return namespace


def build_default_end_output_schema() -> dict[str, Any]:
    return {
        "name": "workflow_result",
        "mode": "simple",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "response": {"type": "string"},
            },
            "required": ["response"],
        },
    }


def build_default_end_output_bindings() -> list[dict[str, Any]]:
    return [
        {
            "json_pointer": "/response",
            "value_ref": {
                "namespace": "workflow_input",
                "key": "text",
                "label": "Workflow input / text",
            },
        }
    ]


def normalize_state_variable_definition(raw: Any) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    key = str(item.get("key") or item.get("name") or "").strip()
    value_type = normalize_value_type(item.get("type"))
    normalized: dict[str, Any] = {
        "key": key,
        "type": value_type,
    }
    if "default_value" in item:
        normalized["default_value"] = item.get("default_value")
    elif "default" in item:
        normalized["default_value"] = item.get("default")
    return normalized


def normalize_set_state_assignment(raw: Any) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    key = str(item.get("key") or item.get("variable") or "").strip()
    normalized: dict[str, Any] = {"key": key}
    if "value_ref" in item and isinstance(item.get("value_ref"), dict):
        normalized["value_ref"] = dict(item.get("value_ref") or {})
    if "value" in item:
        normalized["value"] = item.get("value")
    if "type" in item or "value_type" in item:
        normalized["type"] = normalize_value_type(item.get("type") or item.get("value_type"))
    return normalized


def normalize_value_ref(raw: Any) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    normalized = {
        "namespace": normalize_value_ref_namespace(item.get("namespace")),
        "key": str(item.get("key") or "").strip(),
    }
    if item.get("node_id") is not None:
        normalized["node_id"] = str(item.get("node_id") or "").strip()
    if item.get("expected_type") is not None:
        normalized["expected_type"] = normalize_value_type(item.get("expected_type"))
    if item.get("label") is not None:
        normalized["label"] = str(item.get("label") or "").strip()
    return normalized


def resolve_operator_display_name(operator_spec: Any | None, node_type: str) -> str | None:
    if operator_spec is not None:
        for attr in ("display_name", "displayName", "name"):
            value = str(getattr(operator_spec, attr, "") or "").strip()
            if value:
                return value
        ui = getattr(operator_spec, "ui", None)
        if isinstance(ui, dict):
            for key in ("display_name", "displayName", "name", "title"):
                value = str(ui.get(key) or "").strip()
                if value:
                    return value
    return str(node_type or "").replace("_", " ").strip().title() or None


def _node_data_value(node: Any, key: str) -> str | None:
    data = getattr(node, "data", None)
    if isinstance(data, dict):
        value = str(data.get(key) or "").strip()
        return value or None
    return None


def resolve_node_display_name(node: Any, *, operator_spec: Any | None = None, node_type: str | None = None) -> str:
    config = getattr(node, "config", None)
    if isinstance(config, dict):
        for key in ("name", "label"):
            value = str(config.get(key) or "").strip()
            if value:
                return value

    data_display_name = _node_data_value(node, "displayName")
    if data_display_name:
        return data_display_name

    direct_label = str(getattr(node, "label", "") or "").strip()
    if direct_label:
        return direct_label

    operator_display = resolve_operator_display_name(operator_spec, str(node_type or getattr(node, "type", "") or ""))
    if operator_display:
        return operator_display

    return str(getattr(node, "id", "") or node_type or "node").strip() or "node"


def _build_template_suggestion(
    *,
    suggestion_id: str,
    display_label: str,
    insert_text: str,
    value_type: Any,
    namespace: str,
    key: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "id": suggestion_id,
        "display_label": display_label,
        "insert_text": insert_text,
        "type": normalize_value_type(value_type),
        "namespace": namespace,
        "key": key,
    }
    if node_id:
        payload["node_id"] = node_id
    return payload


def normalize_end_output_config(config: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(config or {})
    if not isinstance(raw.get("output_schema"), dict):
        raw["output_schema"] = build_default_end_output_schema()
    else:
        output_schema = dict(raw["output_schema"])
        output_schema.setdefault("name", "workflow_result")
        output_schema.setdefault("mode", "simple")
        if not isinstance(output_schema.get("schema"), dict):
            output_schema["schema"] = build_default_end_output_schema()["schema"]
        raw["output_schema"] = output_schema

    bindings = raw.get("output_bindings")
    if not isinstance(bindings, list):
        raw["output_bindings"] = build_default_end_output_bindings()
    else:
        normalized_bindings: list[dict[str, Any]] = []
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            value_ref = normalize_value_ref(binding.get("value_ref"))
            normalized_bindings.append(
                {
                    "json_pointer": str(binding.get("json_pointer") or "").strip(),
                    "value_ref": value_ref,
                }
            )
        raw["output_bindings"] = normalized_bindings
    return raw


def get_node_output_contract(
    *,
    node_id: str,
    node_type: str,
    node_label: str | None,
    config: dict[str, Any] | None,
    operator_spec: Any | None,
) -> dict[str, Any]:
    config = dict(config or {})
    contract = operator_spec.output_contract if operator_spec and isinstance(getattr(operator_spec, "output_contract", None), dict) else {}
    fields = contract.get("fields") if isinstance(contract.get("fields"), list) else None

    # Agent/LLM outputs are config-dependent. Do not trust a static registry
    # contract here because the builder should only see the active output mode.
    if node_type == "agent":
        fields = None

    if fields is None:
        artifact_output_schema = config.get("_artifact_output_schema")
        artifact_ui = config.get("_artifact_node_ui") if isinstance(config.get("_artifact_node_ui"), dict) else {}
        artifact_output_hints = artifact_ui.get("outputs") if isinstance(artifact_ui.get("outputs"), list) else []
        artifact_labels = {
            str(item.get("name") or "").strip(): str(item.get("label") or item.get("title") or item.get("name") or "").strip()
            for item in artifact_output_hints
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        if isinstance(artifact_output_schema, dict):
            fields = contract_fields_from_schema(
                artifact_output_schema,
                fallback_key="result",
                labels_by_key=artifact_labels,
            )

    if fields is None:
        if node_type == "agent":
            if str(config.get("output_format") or "").strip().lower() == "json" or isinstance(config.get("output_schema"), dict):
                fields = [{"key": "output_json", "type": "unknown", "label": "Output JSON"}]
            else:
                fields = [{"key": "output_text", "type": "string", "label": "Output Text"}]
        elif node_type == "tool":
            fields = [{"key": "result", "type": "unknown"}]
        elif node_type in {"rag", "vector_search"}:
            fields = [{"key": "results", "type": "list"}, {"key": "documents", "type": "list"}]
        elif node_type == "classify":
            fields = [
                {"key": "category", "type": "string"},
                {"key": "branch_id", "type": "string", "label": "Branch ID"},
                {"key": "classification_result", "type": "string", "label": "Classification Result"},
            ]
        elif node_type == "transform":
            fields = [{"key": "output", "type": "unknown"}]
        elif node_type == "speech_to_text":
            fields = [
                {"key": "text", "type": "string"},
                {"key": "segments", "type": "list"},
                {"key": "language", "type": "string"},
                {"key": "attachments", "type": "list", "semantic_type": "audio"},
                {"key": "provider_metadata", "type": "object"},
            ]
        elif node_type == "human_input":
            fields = [{"key": "input_text", "type": "string"}]
        elif node_type == "user_approval":
            fields = [{"key": "approved", "type": "boolean"}, {"key": "comment", "type": "string"}]
        else:
            ui_outputs = operator_spec.ui.get("outputs") if operator_spec and isinstance(getattr(operator_spec, "ui", None), dict) else []
            fields = [
                {
                    "key": str(item.get("name") or "").strip(),
                    "type": normalize_value_type(item.get("type")),
                }
                for item in (ui_outputs or [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ]

    normalized_fields = []
    for item in fields or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("name") or "").strip()
        if not key:
            continue
        normalized_fields.append(
            {
                "key": key,
                "type": normalize_value_type(item.get("type")),
                "label": str(item.get("label") or key).strip(),
                "semantic_type": normalize_semantic_type(item.get("semantic_type")),
            }
        )

    return {
        "node_id": node_id,
        "node_type": node_type,
        "node_label": str(node_label or node_id).strip() or node_id,
        "fields": normalized_fields,
    }


def _build_workflow_input_inventory(graph: Any) -> list[dict[str, Any]]:
    workflow_contract = getattr(graph, "workflow_contract", None)
    inputs = getattr(workflow_contract, "inputs", None) if workflow_contract is not None else None
    inventory: list[dict[str, Any]] = []
    for item in inputs or []:
        key = str(getattr(item, "key", "") or "").strip()
        if not key:
            continue
        if getattr(item, "enabled", True) is False:
            continue
        inventory.append(
            {
                "namespace": "workflow_input",
                "key": key,
                "type": normalize_value_type(getattr(item, "type", None)),
                "label": str(getattr(item, "label", None) or key).strip() or key,
                "description": str(getattr(item, "description", None) or "").strip() or None,
                "enabled": bool(getattr(item, "enabled", True)),
                "readonly": bool(getattr(item, "readonly", True)),
                "required": bool(getattr(item, "required", False)),
                "derived": bool(getattr(item, "derived", False)),
                "semantic_type": normalize_semantic_type(getattr(item, "semantic_type", None)),
            }
        )
    return inventory


def _build_state_inventory(graph: Any, *, errors: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    state_inventory: list[dict[str, Any]] = []
    state_by_key: dict[str, dict[str, Any]] = {}
    state_contract = getattr(graph, "state_contract", None)
    variables = getattr(state_contract, "variables", None) if state_contract is not None else None
    start_nodes = graph.get_input_nodes() if hasattr(graph, "get_input_nodes") else []
    start_node = start_nodes[0] if start_nodes else None

    for raw_var in variables or []:
        item = normalize_state_variable_definition(raw_var.model_dump() if hasattr(raw_var, "model_dump") else raw_var)
        key = item["key"]
        if not key:
            errors.append({"node_id": getattr(start_node, "id", None), "message": "State variable key is required", "severity": "error"})
            continue
        if not STATE_KEY_RE.match(key):
            errors.append({"node_id": getattr(start_node, "id", None), "message": f"Invalid state variable key: {key}", "severity": "error"})
            continue
        if key in state_by_key:
            errors.append({"node_id": getattr(start_node, "id", None), "message": f"Duplicate state variable key: {key}", "severity": "error"})
            continue
        default_value = item.get("default_value")
        if "default_value" in item and default_value is not None:
            inferred = infer_runtime_value_type(default_value)
            if not value_types_compatible(item["type"], inferred):
                errors.append(
                    {
                        "node_id": getattr(start_node, "id", None),
                        "message": f"Default value type mismatch for state variable '{key}'",
                        "severity": "error",
                    }
                )
                continue
        inventory_item = {
            "namespace": "state",
            "key": key,
            "type": item["type"],
            "label": key,
            "default_value": item.get("default_value"),
        }
        state_by_key[key] = inventory_item
        state_inventory.append(inventory_item)
    return state_inventory, state_by_key


def _compute_upstream_node_ids(graph: Any) -> dict[str, set[str]]:
    direct_sources_by_target: dict[str, list[str]] = {}
    for edge in getattr(graph, "edges", []) or []:
        source = str(getattr(edge, "source", None) or (edge.get("source") if isinstance(edge, dict) else "") or "").strip()
        target = str(getattr(edge, "target", None) or (edge.get("target") if isinstance(edge, dict) else "") or "").strip()
        if not source or not target:
            continue
        direct_sources_by_target.setdefault(target, [])
        if source not in direct_sources_by_target[target]:
            direct_sources_by_target[target].append(source)

    upstream_by_target: dict[str, set[str]] = {}

    def collect(node_id: str, visiting: set[str] | None = None) -> set[str]:
        if node_id in upstream_by_target:
            return set(upstream_by_target[node_id])
        visiting = set(visiting or set())
        if node_id in visiting:
            return set()
        visiting.add(node_id)
        resolved: set[str] = set()
        for source in direct_sources_by_target.get(node_id, []):
            resolved.add(source)
            resolved.update(collect(source, visiting))
        upstream_by_target[node_id] = set(resolved)
        return set(resolved)

    for node in getattr(graph, "nodes", []) or []:
        node_id = str(getattr(node, "id", "") or "").strip()
        if node_id:
            collect(node_id)
    return upstream_by_target


def _scoped_node_output_inventory(
    node_output_inventory: list[dict[str, Any]],
    *,
    allowed_node_ids: set[str],
) -> list[dict[str, Any]]:
    scoped: list[dict[str, Any]] = []
    for group in node_output_inventory:
        group_node_id = str(group.get("node_id") or "").strip()
        if group_node_id and group_node_id in allowed_node_ids:
            scoped.append(copy.deepcopy(group))
    return scoped


def build_graph_analysis(
    *,
    graph: Any,
    operator_lookup: Callable[[str], Any | None],
    normalize_node_type: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    workflow_input_inventory = _build_workflow_input_inventory(graph)
    state_inventory, state_by_key = _build_state_inventory(graph, errors=errors)
    node_output_inventory: list[dict[str, Any]] = []
    operator_contracts: dict[str, Any] = {}
    effective_spec_version = str(getattr(graph, "spec_version", None) or GRAPH_SPEC_V1)
    direct_incoming_sources_by_target: dict[str, list[str]] = {}

    for edge in getattr(graph, "edges", []) or []:
        source = str(getattr(edge, "source", None) or (edge.get("source") if isinstance(edge, dict) else "") or "").strip()
        target = str(getattr(edge, "target", None) or (edge.get("target") if isinstance(edge, dict) else "") or "").strip()
        if not source or not target:
            continue
        direct_incoming_sources_by_target.setdefault(target, [])
        if source not in direct_incoming_sources_by_target[target]:
            direct_incoming_sources_by_target[target].append(source)

    upstream_node_ids_by_target = _compute_upstream_node_ids(graph)

    node_output_lookup: dict[str, dict[str, Any]] = {}
    for node in getattr(graph, "nodes", []):
        normalized_type = normalize_node_type(str(node.type)) if normalize_node_type else str(node.type)
        operator_spec = operator_lookup(normalized_type)
        operator_contracts[normalized_type] = {
            "field_contracts": dict(getattr(operator_spec, "field_contracts", {}) or {}) if operator_spec else {},
            "output_contract": dict(getattr(operator_spec, "output_contract", {}) or {}) if operator_spec else {},
        }
        allowed_upstream_node_ids = upstream_node_ids_by_target.get(str(node.id), set())
        field_contracts = operator_contracts[normalized_type]["field_contracts"]
        config = node.config if isinstance(node.config, dict) else {}

        for field_name, contract in field_contracts.items():
            if not isinstance(contract, dict) or str(contract.get("type") or "").strip() != "value_ref":
                continue
            raw_value = config.get(field_name)
            if raw_value in (None, ""):
                continue
            value_ref = normalize_value_ref(raw_value)
            ref_type, ref_item = resolve_value_ref_type(
                inventory={
                    "workflow_input": workflow_input_inventory,
                    "state": state_inventory,
                    "node_outputs": node_output_inventory,
                },
                value_ref=value_ref,
                allowed_node_ids=allowed_upstream_node_ids,
                return_item=True,
            )
            if ref_type is None:
                errors.append(
                    {
                        "node_id": node.id,
                        "message": f"Field '{field_name}' references unavailable value: {value_ref}",
                        "severity": "error",
                    }
                )
                continue
            allowed_types = contract.get("allowed_types") if isinstance(contract.get("allowed_types"), list) else []
            if allowed_types and not any(value_types_compatible(expected, ref_type) for expected in allowed_types):
                errors.append(
                    {
                        "node_id": node.id,
                        "message": f"Field '{field_name}' type mismatch: expected {allowed_types}, got {ref_type}",
                        "severity": "error",
                    }
                )
            allowed_semantic_types = contract.get("allowed_semantic_types") if isinstance(contract.get("allowed_semantic_types"), list) else []
            if allowed_semantic_types and ref_item is not None:
                actual_semantic_type = ref_item.get("semantic_type")
                if not any(semantic_types_compatible(expected, actual_semantic_type) for expected in allowed_semantic_types):
                    errors.append(
                        {
                            "node_id": node.id,
                            "message": f"Field '{field_name}' semantic type mismatch: expected {allowed_semantic_types}, got {actual_semantic_type or 'unknown'}",
                            "severity": "error",
                        }
                    )
        if normalized_type == "set_state":
            assignments = config.get("assignments") if isinstance(config.get("assignments"), list) else []
            for raw_assignment in assignments:
                assignment = normalize_set_state_assignment(raw_assignment)
                key = assignment["key"]
                if not key:
                    errors.append({"node_id": node.id, "message": "Set State assignment key is required", "severity": "error"})
                    continue
                if not STATE_KEY_RE.match(key):
                    errors.append({"node_id": node.id, "message": f"Invalid state variable key: {key}", "severity": "error"})
                    continue
                declared_type = normalize_value_type(assignment.get("type"))
                if key not in state_by_key:
                    if effective_spec_version in {GRAPH_SPEC_V3, GRAPH_SPEC_V4} and declared_type == "unknown":
                        errors.append(
                            {
                                "node_id": node.id,
                                "message": f"Set State assignment '{key}' must declare a type when creating a new key",
                                "severity": "error",
                            }
                        )
                        continue
                    state_item = {
                        "namespace": "state",
                        "key": key,
                        "type": declared_type,
                        "label": key,
                        "created_by_node_id": node.id,
                    }
                    state_by_key[key] = state_item
                    state_inventory.append(state_item)
                elif declared_type != "unknown" and not value_types_compatible(state_by_key[key]["type"], declared_type):
                    errors.append(
                        {
                            "node_id": node.id,
                            "message": f"Set State assignment '{key}' has incompatible type",
                            "severity": "error",
                        }
                    )
                    continue

                value_ref = assignment.get("value_ref")
                if isinstance(value_ref, dict):
                    ref_type = resolve_value_ref_type(
                        inventory={
                            "workflow_input": workflow_input_inventory,
                            "state": state_inventory,
                            "node_outputs": node_output_inventory,
                        },
                        value_ref=normalize_value_ref(value_ref),
                        allowed_node_ids=allowed_upstream_node_ids,
                    )
                    if ref_type is None:
                        errors.append(
                            {
                                "node_id": node.id,
                                "message": f"Set State assignment '{key}' references unknown value: {value_ref}",
                                "severity": "error",
                            }
                        )
                        continue

                    expected_type = normalize_value_type(state_by_key[key]["type"])
                    if declared_type != "unknown":
                        expected_type = declared_type
                    if expected_type != "unknown" and not value_types_compatible(expected_type, ref_type):
                        errors.append(
                            {
                                "node_id": node.id,
                                "message": f"Set State assignment '{key}' type mismatch: expected {expected_type}, got {ref_type}",
                                "severity": "error",
                            }
                        )

        output_contract = get_node_output_contract(
            node_id=node.id,
            node_type=normalized_type,
            node_label=resolve_node_display_name(node, operator_spec=operator_spec, node_type=normalized_type),
            config=node.config if isinstance(node.config, dict) else {},
            operator_spec=operator_spec,
        )
        if output_contract["fields"] and not operator_contracts[normalized_type]["output_contract"]:
            operator_contracts[normalized_type]["output_contract"] = {
                "fields": [dict(item) for item in output_contract["fields"]],
            }
        node_output_lookup[node.id] = {item["key"]: item for item in output_contract["fields"]}
        if output_contract["fields"]:
            node_output_inventory.append(output_contract)

    template_global_suggestions: list[dict[str, Any]] = []
    for item in workflow_input_inventory:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        template_global_suggestions.append(
            _build_template_suggestion(
                suggestion_id=f"workflow_input:{key}",
                display_label=str(item.get("label") or key).strip() or key,
                insert_text=f"workflow_input.{key}",
                value_type=item.get("type"),
                namespace="workflow_input",
                key=key,
            )
        )

    for item in state_inventory:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        template_global_suggestions.append(
            _build_template_suggestion(
                suggestion_id=f"state:{key}",
                display_label=str(item.get("label") or key).strip() or key,
                insert_text=f"state.{key}",
                value_type=item.get("type"),
                namespace="state",
                key=key,
            )
        )

    template_suggestions_by_node: dict[str, list[dict[str, Any]]] = {}
    accessible_node_outputs_by_node: dict[str, list[dict[str, Any]]] = {}
    for node in getattr(graph, "nodes", []) or []:
        node_id = str(getattr(node, "id", "") or "").strip()
        if not node_id:
            continue
        accessible_node_outputs_by_node[node_id] = _scoped_node_output_inventory(
            node_output_inventory,
            allowed_node_ids=upstream_node_ids_by_target.get(node_id, set()),
        )
        scoped: list[dict[str, Any]] = []
        seen_suggestion_ids: set[str] = set()
        for source_node_id in direct_incoming_sources_by_target.get(node_id, []):
            output_group = next((group for group in node_output_inventory if str(group.get("node_id")) == source_node_id), None)
            if not output_group:
                continue
            node_label = str(output_group.get("node_label") or source_node_id).strip() or source_node_id
            for field in output_group.get("fields", []):
                field_key = str(field.get("key") or "").strip()
                if not field_key:
                    continue
                suggestion_id = f"node_output:{source_node_id}:{field_key}"
                if suggestion_id in seen_suggestion_ids:
                    continue
                seen_suggestion_ids.add(suggestion_id)
                scoped.append(
                    _build_template_suggestion(
                        suggestion_id=suggestion_id,
                        display_label=f"{node_label} / {str(field.get('label') or field_key).strip() or field_key}",
                        insert_text=f"upstream.{source_node_id}.{field_key}",
                        value_type=field.get("type"),
                        namespace="node_output",
                        key=field_key,
                        node_id=source_node_id,
                    )
                )
        template_suggestions_by_node[node_id] = scoped

    end_nodes = graph.get_output_nodes() if hasattr(graph, "get_output_nodes") else []
    for end_node in end_nodes:
        if effective_spec_version not in {GRAPH_SPEC_V3, GRAPH_SPEC_V4}:
            continue
        end_config = normalize_end_output_config(end_node.config if isinstance(end_node.config, dict) else {})
        output_schema = end_config.get("output_schema") if isinstance(end_config.get("output_schema"), dict) else {}
        schema_payload = output_schema.get("schema") if isinstance(output_schema.get("schema"), dict) else {}
        try:
            jsonschema.Draft7Validator.check_schema(schema_payload)
        except Exception as exc:
            errors.append({"node_id": end_node.id, "message": f"Invalid End output schema: {exc}", "severity": "error"})
            continue

        bindings = end_config.get("output_bindings") if isinstance(end_config.get("output_bindings"), list) else []
        required_pointers = required_schema_pointers(schema_payload)
        seen_pointers: set[str] = set()

        for raw_binding in bindings:
            if not isinstance(raw_binding, dict):
                continue
            json_pointer = str(raw_binding.get("json_pointer") or "").strip()
            value_ref = normalize_value_ref(raw_binding.get("value_ref"))
            if not json_pointer:
                errors.append({"node_id": end_node.id, "message": "End output binding json_pointer is required", "severity": "error"})
                continue
            schema_node = resolve_schema_pointer(schema_payload, json_pointer)
            if schema_node is None:
                errors.append({"node_id": end_node.id, "message": f"End output binding points to unknown schema path: {json_pointer}", "severity": "error"})
                continue
            ref_type = resolve_value_ref_type(
                inventory={
                    "workflow_input": workflow_input_inventory,
                    "state": state_inventory,
                    "node_outputs": node_output_inventory,
                },
                value_ref=value_ref,
                allowed_node_ids=upstream_node_ids_by_target.get(str(end_node.id), set()),
            )
            if ref_type is None:
                errors.append({"node_id": end_node.id, "message": f"End output binding references unknown value: {value_ref}", "severity": "error"})
                continue
            expected_type = schema_to_value_type(schema_node)
            if not value_types_compatible(expected_type, ref_type):
                errors.append(
                    {
                        "node_id": end_node.id,
                        "message": f"End output binding type mismatch for {json_pointer}: expected {expected_type}, got {ref_type}",
                        "severity": "error",
                    }
                )
                continue
            seen_pointers.add(json_pointer)

        for required_pointer in required_pointers:
            if required_pointer not in seen_pointers:
                errors.append(
                    {
                        "node_id": end_node.id,
                        "message": f"Missing required End output binding for {required_pointer}",
                        "severity": "error",
                    }
                )

    return {
        "spec_version": effective_spec_version,
        "inventory": {
            "workflow_input": workflow_input_inventory,
            "state": state_inventory,
            "node_outputs": node_output_inventory,
            "accessible_node_outputs_by_node": accessible_node_outputs_by_node,
            "template_suggestions": {
                "global": template_global_suggestions,
                "by_node": template_suggestions_by_node,
            },
        },
        "operator_contracts": operator_contracts,
        "errors": errors,
        "warnings": warnings,
    }


def resolve_value_ref_type(
    *,
    inventory: dict[str, Any],
    value_ref: dict[str, Any],
    allowed_node_ids: set[str] | None = None,
    return_item: bool = False,
) -> str | tuple[str | None, dict[str, Any] | None] | None:
    namespace = normalize_value_ref_namespace(value_ref.get("namespace"))
    key = str(value_ref.get("key") or "").strip()
    node_id = str(value_ref.get("node_id") or "").strip()

    def _result(value_type: str | None, item: dict[str, Any] | None = None):
        if return_item:
            return value_type, item
        return value_type

    if not key:
        return _result(None)
    if namespace == "workflow_input":
        for item in inventory.get("workflow_input", []):
            if str(item.get("key")) == key:
                return _result(normalize_value_type(item.get("type")), item)
        return _result(None)
    if namespace == "state":
        for item in inventory.get("state", []):
            if str(item.get("key")) == key:
                return _result(normalize_value_type(item.get("type")), item)
        return _result(None)
    if namespace == "node_output":
        if not node_id:
            return _result(None)
        if allowed_node_ids is not None and node_id not in allowed_node_ids:
            return _result(None)
        for group in inventory.get("node_outputs", []):
            if str(group.get("node_id")) != node_id:
                continue
            for item in group.get("fields", []):
                if str(item.get("key")) == key:
                    return _result(normalize_value_type(item.get("type")), item)
        return _result(None)
    return _result(None)


def resolve_runtime_value_ref(*, state: dict[str, Any], value_ref: dict[str, Any]) -> Any:
    namespace = normalize_value_ref_namespace(value_ref.get("namespace"))
    key = str(value_ref.get("key") or "").strip()
    node_id = str(value_ref.get("node_id") or "").strip()
    if namespace == "workflow_input":
        workflow_input = state.get("workflow_input") if isinstance(state.get("workflow_input"), dict) else {}
        return workflow_input.get(key)
    if namespace == "state":
        state_payload = state.get("state") if isinstance(state.get("state"), dict) else {}
        return state_payload.get(key)
    if namespace == "node_output":
        node_outputs = state.get("node_outputs") if isinstance(state.get("node_outputs"), dict) else {}
        node_payload = node_outputs.get(node_id) if isinstance(node_outputs.get(node_id), dict) else {}
        return node_payload.get(key)
    return None


def required_schema_pointers(schema: dict[str, Any], pointer: str = "") -> list[str]:
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    pointers: list[str] = []
    for key in required:
        child_pointer = f"{pointer}/{escape_json_pointer_token(str(key))}"
        pointers.append(child_pointer or "/")
        child_schema = properties.get(key)
        if isinstance(child_schema, dict):
            pointers.extend(required_schema_pointers(child_schema, child_pointer))
    return pointers


def escape_json_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def unescape_json_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def resolve_schema_pointer(schema: dict[str, Any], pointer: str) -> dict[str, Any] | None:
    if pointer in {"", "/"}:
        return schema
    if not pointer.startswith("/"):
        return None
    current: Any = schema
    for raw_token in pointer.split("/")[1:]:
        token = unescape_json_pointer_token(raw_token)
        if not isinstance(current, dict):
            return None
        properties = current.get("properties") if isinstance(current.get("properties"), dict) else {}
        if token in properties:
            current = properties[token]
            continue
        items = current.get("items")
        if token.isdigit() and isinstance(items, dict):
            current = items
            continue
        return None
    return current if isinstance(current, dict) else None


def materialize_end_output(*, config: dict[str, Any], state: dict[str, Any]) -> Any:
    normalized = normalize_end_output_config(config)
    output_schema = normalized["output_schema"]
    schema_payload = output_schema["schema"]
    bindings = normalized.get("output_bindings") or []
    materialized = _seed_output_from_schema(schema_payload)
    root_assigned = False

    for binding in bindings:
        json_pointer = str(binding.get("json_pointer") or "").strip()
        value_ref = normalize_value_ref(binding.get("value_ref"))
        value = resolve_runtime_value_ref(state=state, value_ref=value_ref)
        if json_pointer in {"", "/"}:
            materialized = value
            root_assigned = True
            continue
        _assign_json_pointer(materialized, json_pointer, value)

    if root_assigned:
        jsonschema.validate(instance=materialized, schema=schema_payload)
        return materialized

    jsonschema.validate(instance=materialized, schema=schema_payload)
    return materialized


def _seed_output_from_schema(schema: dict[str, Any]) -> Any:
    schema_type = schema_to_value_type(schema)
    if schema_type == "object":
        return {}
    if schema_type == "list":
        return []
    return None


def _assign_json_pointer(target: Any, pointer: str, value: Any) -> None:
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid json pointer: {pointer}")
    tokens = [unescape_json_pointer_token(token) for token in pointer.split("/")[1:]]
    current = target
    for index, token in enumerate(tokens):
        is_last = index == len(tokens) - 1
        next_token = tokens[index + 1] if not is_last else None
        if isinstance(current, dict):
            if is_last:
                current[token] = value
                return
            if token not in current or current[token] is None:
                current[token] = [] if next_token and next_token.isdigit() else {}
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdigit():
                raise ValueError(f"Invalid list pointer token: {token}")
            numeric = int(token)
            while len(current) <= numeric:
                current.append(None)
            if is_last:
                current[numeric] = value
                return
            if current[numeric] is None:
                current[numeric] = [] if next_token and next_token.isdigit() else {}
            current = current[numeric]
            continue
        raise ValueError(f"Cannot assign json pointer {pointer}")


def extract_runtime_node_output(
    *,
    node_type: str,
    config: dict[str, Any] | None,
    operator_spec: Any | None = None,
    state_update: dict[str, Any],
    previous_state: dict[str, Any],
) -> dict[str, Any]:
    state_update = dict(state_update or {})
    previous_state = dict(previous_state or {})
    raw_output: dict[str, Any] = {}

    if node_type == "agent":
        state_payload = state_update.get("state") if isinstance(state_update.get("state"), dict) else {}
        last_output = state_payload.get("last_agent_output")
        if isinstance(last_output, (dict, list)):
            raw_output = {"output_json": last_output}
        elif last_output is not None:
            raw_output = {"output_text": str(last_output)}
        else:
            raw_output = {}

    elif node_type == "tool":
        tool_outputs = state_update.get("tool_outputs")
        if isinstance(tool_outputs, list) and tool_outputs:
            raw_output = {"result": tool_outputs[0]}
        elif "context" in state_update:
            raw_output = {"result": state_update.get("context")}
        else:
            raw_output = {}

    elif node_type in {"rag", "vector_search"}:
        rag_output = state_update.get("rag_output")
        if isinstance(rag_output, list):
            raw_output = {"results": rag_output, "documents": rag_output}
        else:
            context = state_update.get("context") if isinstance(state_update.get("context"), dict) else {}
            search_results = context.get("search_results")
            if isinstance(search_results, list):
                raw_output = {"results": search_results, "documents": search_results}
            else:
                raw_output = {}

    elif node_type == "classify":
        payload = {
            "category": state_update.get("category") or state_update.get("branch_label") or state_update.get("classification_result"),
        }
        if state_update.get("branch_id") is not None:
            payload["branch_id"] = state_update.get("branch_id")
        if state_update.get("classification_result") is not None:
            payload["classification_result"] = state_update.get("classification_result")
        raw_output = payload

    elif node_type == "transform":
        if "transform_output" in state_update:
            raw_output = {"output": state_update.get("transform_output")}
        else:
            raw_output = {}

    elif node_type == "speech_to_text":
        stt_output = state_update.get("stt_output")
        if isinstance(stt_output, dict):
            raw_output = dict(stt_output)
        else:
            raw_output = {}

    elif node_type == "human_input":
        messages = state_update.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                raw_output = {"input_text": last.get("content")}
            else:
                raw_output = {}
        else:
            raw_output = {}

    elif node_type == "user_approval":
        raw_output = {
            "approved": state_update.get("branch_taken") == "approve",
            "comment": (state_update.get("context") or {}).get("comment") if isinstance(state_update.get("context"), dict) else None,
        }

    elif node_type == "set_state":
        next_state = state_update.get("state") if isinstance(state_update.get("state"), dict) else {}
        prev_state = previous_state.get("state") if isinstance(previous_state.get("state"), dict) else {}
        changed: dict[str, Any] = {}
        for key, value in next_state.items():
            if prev_state.get(key) != value:
                changed[key] = value
        raw_output = changed

    elif node_type == "end":
        if "final_output" in state_update:
            raw_output = {"final_output": state_update.get("final_output")}

    elif isinstance(state_update, dict):
        raw_output = {
            str(key): value
            for key, value in state_update.items()
            if str(key).strip() and not str(key).startswith("_")
        }

    if node_type == "set_state":
        return {}
    if node_type == "end":
        return raw_output

    declared = get_node_output_contract(
        node_id="_runtime",
        node_type=node_type,
        node_label=node_type,
        config=config,
        operator_spec=operator_spec,
    )
    declared_keys = {
        str(item.get("key") or "").strip()
        for item in declared.get("fields", [])
        if isinstance(item, dict) and str(item.get("key") or "").strip()
    }
    if not declared_keys:
        return {}
    if declared_keys == {"result"} and "result" not in raw_output and raw_output:
        return {"result": raw_output}
    return {
        key: value
        for key, value in raw_output.items()
        if key in declared_keys and value is not None
    }
