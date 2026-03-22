from __future__ import annotations

import copy
import re
from typing import Any, Callable

import jsonschema

from app.agent.graph.ir import GRAPH_SPEC_V1, GRAPH_SPEC_V3


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
                "key": "input_as_text",
                "label": "Workflow input / input_as_text",
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
            fields = [{"key": "output_text", "type": "string"}]
            if str(config.get("output_format") or "").strip().lower() == "json" or isinstance(config.get("output_schema"), dict):
                fields.append({"key": "output_json", "type": "unknown"})
        elif node_type == "llm":
            fields = [{"key": "output_text", "type": "string"}]
            if str(config.get("output_format") or "").strip().lower() == "json" or isinstance(config.get("output_schema"), dict):
                fields.append({"key": "output_json", "type": "unknown"})
        elif node_type == "tool":
            fields = [{"key": "result", "type": "unknown"}]
        elif node_type in {"rag", "vector_search"}:
            fields = [{"key": "results", "type": "list"}, {"key": "documents", "type": "list"}]
        elif node_type == "classify":
            fields = [{"key": "category", "type": "string"}, {"key": "confidence", "type": "number"}]
        elif node_type == "transform":
            fields = [{"key": "output", "type": "unknown"}]
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
            }
        )

    return {
        "node_id": node_id,
        "node_type": node_type,
        "node_label": node_label or node_id,
        "fields": normalized_fields,
    }


def _template_variable_entries(item: dict[str, Any]) -> list[dict[str, Any]]:
    namespace = str(item.get("namespace") or "")
    key = str(item.get("key") or "")
    node_id = str(item.get("node_id") or "")
    value_type = normalize_value_type(item.get("type"))
    label = str(item.get("label") or key).strip()
    entries: list[dict[str, Any]] = []

    if namespace == "workflow_input":
        canonical = f"workflow_input.{key}"
        entries.append({"name": canonical, "type": value_type, "label": label, "namespace": namespace, "key": key})
        entries.append({"name": key, "type": value_type, "label": label, "namespace": namespace, "key": key})
    elif namespace == "state":
        canonical = f"state.{key}"
        entries.append({"name": canonical, "type": value_type, "label": label, "namespace": namespace, "key": key})
        entries.append({"name": key, "type": value_type, "label": label, "namespace": namespace, "key": key})
    elif namespace == "node_output" and node_id:
        canonical = f"node_outputs.{node_id}.{key}"
        upstream_alias = f"upstream.{node_id}.{key}"
        entries.append({"name": canonical, "type": value_type, "label": label, "namespace": namespace, "key": key, "node_id": node_id})
        entries.append({"name": upstream_alias, "type": value_type, "label": label, "namespace": namespace, "key": key, "node_id": node_id})
    return entries


def build_graph_analysis(
    *,
    graph: Any,
    operator_lookup: Callable[[str], Any | None],
    normalize_node_type: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    state_inventory: list[dict[str, Any]] = []
    state_by_key: dict[str, dict[str, Any]] = {}
    node_output_inventory: list[dict[str, Any]] = []
    template_variables: list[dict[str, Any]] = []
    operator_contracts: dict[str, Any] = {}
    effective_spec_version = str(getattr(graph, "spec_version", None) or GRAPH_SPEC_V1)

    workflow_input_inventory = [
        {
            "namespace": "workflow_input",
            "key": "input_as_text",
            "type": "string",
            "label": "Input as text",
            "readonly": True,
        }
    ]

    start_nodes = graph.get_input_nodes() if hasattr(graph, "get_input_nodes") else []
    start_node = start_nodes[0] if start_nodes else None
    start_config = dict(getattr(start_node, "config", {}) or {})
    state_variables = start_config.get("state_variables") if isinstance(start_config.get("state_variables"), list) else []

    for raw_var in state_variables:
        item = normalize_state_variable_definition(raw_var)
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

    node_output_lookup: dict[str, dict[str, Any]] = {}
    for node in getattr(graph, "nodes", []):
        normalized_type = normalize_node_type(str(node.type)) if normalize_node_type else str(node.type)
        operator_spec = operator_lookup(normalized_type)
        operator_contracts[normalized_type] = {
            "field_contracts": dict(getattr(operator_spec, "field_contracts", {}) or {}) if operator_spec else {},
            "output_contract": dict(getattr(operator_spec, "output_contract", {}) or {}) if operator_spec else {},
        }
        if normalized_type == "set_state":
            assignments = node.config.get("assignments") if isinstance(node.config, dict) and isinstance(node.config.get("assignments"), list) else []
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
                    if effective_spec_version == GRAPH_SPEC_V3 and declared_type == "unknown":
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
            node_label=getattr(node, "label", None),
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

    for item in workflow_input_inventory:
        template_variables.extend(_template_variable_entries(item))
    for item in state_inventory:
        template_variables.extend(_template_variable_entries(item))
    for output_group in node_output_inventory:
        for field in output_group["fields"]:
            template_variables.extend(
                _template_variable_entries(
                    {
                        "namespace": "node_output",
                        "node_id": output_group["node_id"],
                        "key": field["key"],
                        "type": field["type"],
                        "label": f"{output_group['node_label']} / {field['label']}",
                    }
                )
            )

    end_nodes = graph.get_output_nodes() if hasattr(graph, "get_output_nodes") else []
    for end_node in end_nodes:
        if effective_spec_version != GRAPH_SPEC_V3:
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
            "template_variables": template_variables,
        },
        "operator_contracts": operator_contracts,
        "errors": errors,
        "warnings": warnings,
    }


def resolve_value_ref_type(*, inventory: dict[str, Any], value_ref: dict[str, Any]) -> str | None:
    namespace = normalize_value_ref_namespace(value_ref.get("namespace"))
    key = str(value_ref.get("key") or "").strip()
    node_id = str(value_ref.get("node_id") or "").strip()
    if not key:
        return None
    if namespace == "workflow_input":
        for item in inventory.get("workflow_input", []):
            if str(item.get("key")) == key:
                return normalize_value_type(item.get("type"))
        return None
    if namespace == "state":
        for item in inventory.get("state", []):
            if str(item.get("key")) == key:
                return normalize_value_type(item.get("type"))
        return None
    if namespace == "node_output":
        if not node_id:
            return None
        for group in inventory.get("node_outputs", []):
            if str(group.get("node_id")) != node_id:
                continue
            for item in group.get("fields", []):
                if str(item.get("key")) == key:
                    return normalize_value_type(item.get("type"))
        return None
    return None


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

    if node_type in {"agent", "llm"}:
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
            "category": state_update.get("branch_taken") or state_update.get("classification_result"),
        }
        if state_update.get("confidence") is not None:
            payload["confidence"] = state_update.get("confidence")
        raw_output = payload

    elif node_type == "transform":
        if "transform_output" in state_update:
            raw_output = {"output": state_update.get("transform_output")}
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
