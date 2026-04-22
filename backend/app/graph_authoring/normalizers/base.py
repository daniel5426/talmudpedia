from __future__ import annotations

from copy import deepcopy
from typing import Any


_MISSING = object()


def apply_schema_defaults(config_schema: dict[str, Any] | None, current_config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config_schema, dict):
        return dict(current_config or {})
    normalized = _apply_schema_defaults(config_schema, current_config if isinstance(current_config, dict) else _MISSING)
    if isinstance(normalized, dict):
        return normalized
    return dict(current_config or {})


def _schema_has_defaults(schema: dict[str, Any] | None) -> bool:
    if not isinstance(schema, dict):
        return False
    if "default" in schema:
        return True
    properties = schema.get("properties")
    if isinstance(properties, dict):
        return any(_schema_has_defaults(value if isinstance(value, dict) else None) for value in properties.values())
    items = schema.get("items")
    if isinstance(items, dict):
        return _schema_has_defaults(items)
    return False


def _apply_schema_defaults(schema: dict[str, Any], value: Any) -> Any:
    if value is _MISSING and "default" in schema:
        return deepcopy(schema.get("default"))

    properties = schema.get("properties")
    schema_type = schema.get("type")
    if isinstance(properties, dict) or schema_type == "object":
        base = dict(value) if isinstance(value, dict) else {}
        for key, property_schema in properties.items() if isinstance(properties, dict) else []:
            prop_schema = property_schema if isinstance(property_schema, dict) else {}
            existing = base[key] if key in base else _MISSING
            normalized = _apply_schema_defaults(prop_schema, existing)
            if normalized is _MISSING:
                continue
            if existing is _MISSING and normalized == {} and "default" not in prop_schema and not _schema_has_defaults(prop_schema):
                continue
            base[key] = normalized
        return base

    items_schema = schema.get("items")
    if schema_type == "array" and isinstance(value, list) and isinstance(items_schema, dict):
        return [
            _apply_schema_defaults(items_schema, item)
            for item in value
        ]

    if value is _MISSING:
        return _MISSING
    return deepcopy(value)
