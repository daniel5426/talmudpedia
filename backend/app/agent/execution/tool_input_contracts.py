from __future__ import annotations

import json
from typing import Any

from jsonschema import ValidationError
from jsonschema.validators import validator_for


def parse_schema_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def get_tool_input_schema(tool: Any) -> dict[str, Any]:
    schema = parse_schema_dict(getattr(tool, "schema", {}) or {})
    input_schema = schema.get("input")
    return input_schema if isinstance(input_schema, dict) else {}


def get_tool_execution_config(tool: Any) -> dict[str, Any]:
    config_schema = parse_schema_dict(getattr(tool, "config_schema", {}) or {})
    execution = config_schema.get("execution")
    return execution if isinstance(execution, dict) else {}


def is_strict_tool_input(tool: Any) -> bool:
    return bool(get_tool_execution_config(tool).get("strict_input_schema"))


def validate_tool_input_schema(tool: Any, input_data: Any) -> list[dict[str, str]]:
    input_schema = get_tool_input_schema(tool)
    if not input_schema:
        return []

    try:
        validator_cls = validator_for(input_schema)
        validator_cls.check_schema(input_schema)
        validator = validator_cls(input_schema)
    except Exception as exc:
        return [{"path": "", "message": f"Invalid tool input schema: {exc}"}]

    errors: list[ValidationError] = sorted(
        validator.iter_errors(input_data),
        key=lambda err: list(err.path),
    )
    normalized: list[dict[str, str]] = []
    for err in errors:
        path = ".".join(str(part) for part in err.path)
        normalized.append(
            {
                "path": path,
                "message": err.message,
            }
        )
    return normalized
