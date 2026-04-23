from __future__ import annotations

from copy import deepcopy
from typing import Any


def required_config_fields(config_schema: dict[str, Any], *, include_runtime: bool = True) -> list[str]:
    raw = config_schema.get("required")
    if not isinstance(raw, list):
        return []
    fields = [str(item) for item in raw if str(item).strip()]
    if include_runtime:
        return fields
    properties = config_schema.get("properties")
    if not isinstance(properties, dict):
        return fields
    filtered: list[str] = []
    for field in fields:
        property_schema = properties.get(field)
        ui_meta = property_schema.get("x-ui") if isinstance(property_schema, dict) else None
        if isinstance(ui_meta, dict) and ui_meta.get("runtime") is True:
            continue
        filtered.append(field)
    return filtered


def _ensure_object_schema(config_schema: dict[str, Any] | None) -> dict[str, Any]:
    base = deepcopy(config_schema) if isinstance(config_schema, dict) else {}
    if base.get("type") != "object":
        base.setdefault("type", "object")
    properties = base.get("properties")
    if not isinstance(properties, dict):
        base["properties"] = {}
    base.setdefault("additionalProperties", True)
    return base


def enrich_schema_with_ui(
    config_schema: dict[str, Any] | None,
    field_specs: list[dict[str, Any]] | None,
    *,
    rows: list[list[str]] | None = None,
) -> dict[str, Any]:
    schema = _ensure_object_schema(config_schema)
    properties = schema["properties"]
    required = set(required_config_fields(schema))
    order: list[str] = []

    for raw_field in list(field_specs or []):
        if not isinstance(raw_field, dict):
            continue
        name = str(raw_field.get("name") or "").strip()
        if not name:
            continue
        order.append(name)
        property_schema = deepcopy(properties.get(name) or {})
        property_schema = property_schema if isinstance(property_schema, dict) else {}
        property_schema.setdefault("title", raw_field.get("label") or name)
        if raw_field.get("description") and "description" not in property_schema:
            property_schema["description"] = raw_field.get("description")
        if raw_field.get("default") is not None and "default" not in property_schema:
            property_schema["default"] = raw_field.get("default")
        if raw_field.get("options") and "enum" not in property_schema:
            property_schema["enum"] = [
                option.get("value") if isinstance(option, dict) else option
                for option in list(raw_field.get("options") or [])
            ]
        json_schema = raw_field.get("json_schema")
        if isinstance(json_schema, dict) and json_schema:
            property_schema = {**deepcopy(json_schema), **property_schema}
        if raw_field.get("minimum") is not None and "minimum" not in property_schema:
            property_schema["minimum"] = raw_field.get("minimum")
        if raw_field.get("maximum") is not None and "maximum" not in property_schema:
            property_schema["maximum"] = raw_field.get("maximum")
        if not any(key in property_schema for key in ("type", "oneOf", "anyOf", "allOf")):
            property_schema["type"] = widget_json_type(str(raw_field.get("fieldType") or ""))

        ui_meta = property_schema.get("x-ui")
        ui_meta = deepcopy(ui_meta) if isinstance(ui_meta, dict) else {}
        ui_meta["widget"] = str(raw_field.get("fieldType") or ui_meta.get("widget") or "string")
        if raw_field.get("runtime") is not None:
            ui_meta["runtime"] = bool(raw_field.get("runtime"))
        if raw_field.get("visibility"):
            ui_meta["visibility"] = raw_field["visibility"]
        if raw_field.get("group"):
            ui_meta["group"] = raw_field["group"]
        if raw_field.get("dependsOn"):
            ui_meta["dependsOn"] = raw_field["dependsOn"]
        if raw_field.get("helpKind"):
            ui_meta["helpKind"] = raw_field["helpKind"]
        if raw_field.get("prompt_capable") is not None:
            ui_meta["promptCapable"] = bool(raw_field.get("prompt_capable"))
        if raw_field.get("prompt_surface"):
            ui_meta["promptSurface"] = raw_field["prompt_surface"]
        if raw_field.get("artifactInputs"):
            ui_meta["artifactInputs"] = raw_field["artifactInputs"]
        if raw_field.get("placeholder"):
            ui_meta["placeholder"] = raw_field["placeholder"]
        property_schema["x-ui"] = ui_meta
        properties[name] = property_schema

        if raw_field.get("required"):
            required.add(name)

    if required:
        schema["required"] = sorted(required)
    elif "required" in schema:
        schema["required"] = []

    root_ui = schema.get("x-ui")
    root_ui = deepcopy(root_ui) if isinstance(root_ui, dict) else {}
    if order:
        root_ui["order"] = order
    if rows:
        root_ui["rows"] = rows
    if root_ui:
        schema["x-ui"] = root_ui
    return schema


def widget_json_type(widget: str) -> str:
    mapping = {
        "number": "number",
        "integer": "integer",
        "boolean": "boolean",
        "json": "object",
        "mapping_list": "array",
        "assignment_list": "array",
        "condition_list": "array",
        "category_list": "array",
        "tool_list": "array",
        "scope_subset": "array",
        "spawn_targets": "array",
        "route_table": "array",
        "field_mapping": "object",
        "value_ref": "object",
        "variable_list": "array",
    }
    return mapping.get(widget, "string")


def schema_for_value_type(value_type: str) -> dict[str, Any]:
    normalized = str(value_type or "").strip().lower()
    if normalized == "string":
        return {"type": "string"}
    if normalized == "number":
        return {"type": "number"}
    if normalized == "boolean":
        return {"type": "boolean"}
    if normalized == "object":
        return {"type": "object", "additionalProperties": True}
    if normalized == "list":
        return {"type": "array"}
    return {}
