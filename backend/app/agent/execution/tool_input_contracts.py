from __future__ import annotations

import json
import re
from typing import Any

from jsonschema import ValidationError
from jsonschema.validators import validator_for


class ToolSchemaValidationError(ValueError):
    def __init__(self, message: str, *, tool_name: str | None = None, schema_path: str | None = None):
        self.tool_name = tool_name
        self.schema_path = schema_path
        parts = []
        if tool_name:
            parts.append(f"tool={tool_name}")
        if schema_path:
            parts.append(f"path={schema_path}")
        prefix = f"[{' '.join(parts)}] " if parts else ""
        super().__init__(prefix + message)


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


_OPTIONAL_METADATA_KEYS = {
    "description",
    "title",
    "format",
    "default",
    "examples",
    "example",
    "x-ui",
    "$comment",
}

_SCHEMA_CONTAINER_KEYS = {
    "properties",
    "items",
    "prefixItems",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "additionalProperties",
}


def _schema_path_to_string(path: tuple[str, ...]) -> str:
    if not path:
        return "input"
    return "input." + ".".join(path)


def _raise_schema_error(message: str, *, tool_name: str | None, path: tuple[str, ...]) -> None:
    raise ToolSchemaValidationError(
        message,
        tool_name=tool_name,
        schema_path=_schema_path_to_string(path),
    )


def sanitize_schema_dict(raw: Any, *, tool_name: str | None = None) -> dict[str, Any]:
    schema = parse_schema_dict(raw)
    if not schema:
        return {}
    sanitized = _sanitize_schema_node(schema, path=(), tool_name=tool_name)
    if not isinstance(sanitized, dict):
        _raise_schema_error("Schema root must be an object.", tool_name=tool_name, path=())
    return sanitized


def _sanitize_schema_node(node: Any, *, path: tuple[str, ...], tool_name: str | None) -> Any:
    if node is None:
        _raise_schema_error("Schema node cannot be null.", tool_name=tool_name, path=path)
    if isinstance(node, bool):
        return node
    if not isinstance(node, dict):
        _raise_schema_error("Schema node must be an object.", tool_name=tool_name, path=path)

    sanitized: dict[str, Any] = {}
    for key, value in node.items():
        if value is None and key in _OPTIONAL_METADATA_KEYS:
            continue
        if key == "properties":
            if not isinstance(value, dict):
                _raise_schema_error("`properties` must be an object.", tool_name=tool_name, path=path + ("properties",))
            props: dict[str, Any] = {}
            for prop_name, prop_schema in value.items():
                if not isinstance(prop_name, str) or not prop_name.strip():
                    _raise_schema_error("Property names must be non-empty strings.", tool_name=tool_name, path=path + ("properties",))
                props[prop_name] = _sanitize_schema_node(
                    prop_schema,
                    path=path + ("properties", prop_name),
                    tool_name=tool_name,
                )
            sanitized[key] = props
            continue
        if key == "required":
            if not isinstance(value, list):
                _raise_schema_error("`required` must be an array.", tool_name=tool_name, path=path + ("required",))
            required: list[str] = []
            for idx, item in enumerate(value):
                if not isinstance(item, str) or not item.strip():
                    _raise_schema_error(
                        "`required` entries must be non-empty strings.",
                        tool_name=tool_name,
                        path=path + ("required", str(idx)),
                    )
                required.append(item)
            sanitized[key] = required
            continue
        if key == "items":
            if isinstance(value, list):
                sanitized[key] = [
                    _sanitize_schema_node(item, path=path + ("items", str(idx)), tool_name=tool_name)
                    for idx, item in enumerate(value)
                ]
            else:
                sanitized[key] = _sanitize_schema_node(value, path=path + ("items",), tool_name=tool_name)
            continue
        if key == "prefixItems":
            if not isinstance(value, list):
                _raise_schema_error("`prefixItems` must be an array.", tool_name=tool_name, path=path + ("prefixItems",))
            sanitized[key] = [
                _sanitize_schema_node(item, path=path + ("prefixItems", str(idx)), tool_name=tool_name)
                for idx, item in enumerate(value)
            ]
            continue
        if key in {"allOf", "anyOf", "oneOf"}:
            if not isinstance(value, list):
                _raise_schema_error(f"`{key}` must be an array.", tool_name=tool_name, path=path + (key,))
            sanitized[key] = [
                _sanitize_schema_node(item, path=path + (key, str(idx)), tool_name=tool_name)
                for idx, item in enumerate(value)
            ]
            continue
        if key in {"not", "if", "then", "else"}:
            sanitized[key] = _sanitize_schema_node(value, path=path + (key,), tool_name=tool_name)
            continue
        if key == "additionalProperties":
            if isinstance(value, (bool, dict)):
                sanitized[key] = (
                    value
                    if isinstance(value, bool)
                    else _sanitize_schema_node(value, path=path + ("additionalProperties",), tool_name=tool_name)
                )
                continue
            _raise_schema_error(
                "`additionalProperties` must be a boolean or schema object.",
                tool_name=tool_name,
                path=path + ("additionalProperties",),
            )
        if value is None and key in _SCHEMA_CONTAINER_KEYS:
            _raise_schema_error(f"`{key}` cannot be null.", tool_name=tool_name, path=path + (key,))
        sanitized[key] = value

    properties = sanitized.get("properties")
    required = sanitized.get("required")
    if isinstance(properties, dict) and isinstance(required, list):
        missing = [item for item in required if item not in properties]
        if missing:
            _raise_schema_error(
                f"`required` references unknown properties: {', '.join(missing)}.",
                tool_name=tool_name,
                path=path + ("required",),
            )
    return sanitized


def get_tool_input_schema(tool: Any) -> dict[str, Any]:
    schema = parse_schema_dict(getattr(tool, "schema", {}) or {})
    input_schema = schema.get("input")
    return input_schema if isinstance(input_schema, dict) else {}


def get_tool_execution_config(tool: Any) -> dict[str, Any]:
    config_schema = parse_schema_dict(getattr(tool, "config_schema", {}) or {})
    execution = config_schema.get("execution")
    return execution if isinstance(execution, dict) else {}


def get_tool_validation_mode(tool: Any) -> str:
    mode = str(get_tool_execution_config(tool).get("validation_mode") or "strict").strip().lower()
    if mode == "none":
        return "none"
    return "strict"


def is_strict_tool_input(tool: Any) -> bool:
    return get_tool_validation_mode(tool) == "strict"


def _path_parts(err: ValidationError) -> list[str]:
    return [str(part) for part in err.path]


def _format_field_name(parts: list[str]) -> str:
    if not parts:
        return "input"
    return ".".join(parts)


def _format_expected_type(value: Any) -> str:
    if isinstance(value, list):
        return " or ".join(str(item) for item in value)
    return str(value)


def _format_actual_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _extract_required_property_name(err: ValidationError) -> str | None:
    if not isinstance(err.message, str):
        return None
    match = re.search(r"'([^']+)' is a required property", err.message)
    return match.group(1) if match else None


def _extract_additional_property_name(err: ValidationError) -> str | None:
    if not isinstance(err.message, str):
        return None
    match = re.search(r"\('([^']+)'\s+was unexpected\)", err.message)
    if match:
        return match.group(1)
    match = re.search(r"'([^']+)'\s+was unexpected", err.message)
    return match.group(1) if match else None


def _branch_required_fields(branch: Any) -> list[str]:
    if not isinstance(branch, dict):
        return []
    required = branch.get("required")
    if not isinstance(required, list):
        return []
    return [str(item) for item in required if isinstance(item, str) and str(item).strip()]


def _summarize_union_validation(err: ValidationError) -> str | None:
    path_parts = _path_parts(err)
    field_name = _format_field_name(path_parts)
    instance = err.instance if isinstance(err.instance, dict) else None
    branches = err.validator_value if isinstance(err.validator_value, list) else []
    branch_requirements = [_branch_required_fields(branch) for branch in branches]
    branch_requirements = [reqs for reqs in branch_requirements if reqs]
    if instance is not None and branch_requirements:
        provided = {str(key) for key in instance.keys()}
        option_text = " or ".join(
            "(" + ", ".join(f"`{name}`" for name in reqs) + ")"
            for reqs in branch_requirements
        )
        missing_by_branch = []
        for reqs in branch_requirements:
            missing = [name for name in reqs if name not in provided]
            if missing:
                missing_by_branch.append(", ".join(f"`{name}`" for name in missing))
        if missing_by_branch:
            missing_text = " or ".join(dict.fromkeys(missing_by_branch))
            return (
                f"`{field_name}` must satisfy one of these field sets: {option_text}. "
                f"Missing fields for matching branches: {missing_text}."
            )
        return f"`{field_name}` must satisfy one of these field sets: {option_text}."

    child_messages: list[str] = []
    for child in err.context[:3]:
        child_path = _format_field_name(_path_parts(child))
        child_messages.append(f"{child_path}: {_format_validation_message(child)}")
    if child_messages:
        label = "one of" if err.validator == "anyOf" else "exactly one of"
        return f"`{field_name}` must match {label} the allowed schema variants. " + " ".join(child_messages)
    return None


def _format_validation_message(err: ValidationError) -> str:
    path_parts = _path_parts(err)
    field_name = _format_field_name(path_parts)

    if err.validator == "required":
        missing = _extract_required_property_name(err)
        if missing:
            target = f"{field_name}.{missing}" if path_parts else missing
            return f"Missing required field `{target}`."

    if err.validator == "type":
        expected = _format_expected_type(err.validator_value)
        actual = _format_actual_type(err.instance)
        return f"`{field_name}` must be {expected}, got {actual}."

    if err.validator == "enum":
        allowed = err.validator_value if isinstance(err.validator_value, list) else []
        allowed_text = ", ".join(f"`{item}`" for item in allowed)
        actual = _format_actual_type(err.instance) if err.instance is not None else "null"
        return f"`{field_name}` must be one of: {allowed_text}. Got {actual}."

    if err.validator == "additionalProperties":
        unexpected = _extract_additional_property_name(err)
        allowed = []
        if isinstance(err.schema, dict):
            properties = err.schema.get("properties")
            if isinstance(properties, dict):
                allowed = sorted(str(key) for key in properties.keys())
        if unexpected:
            message = f"Unexpected field `{unexpected}`."
        else:
            message = f"`{field_name}` contains unexpected fields."
        if allowed:
            allowed_text = ", ".join(f"`{item}`" for item in allowed)
            message += f" Allowed fields: {allowed_text}."
        return message

    if err.validator in {"anyOf", "oneOf"}:
        summary = _summarize_union_validation(err)
        if summary:
            return summary

    return err.message


def _validation_issue_code(err: ValidationError) -> str:
    if err.validator == "required":
        return "missing_required_field"
    if err.validator == "additionalProperties":
        return "unexpected_field"
    if err.validator == "type":
        return "wrong_type"
    if err.validator == "enum":
        return "invalid_enum"
    if err.validator in {"anyOf", "oneOf"}:
        return "schema_branch_mismatch"
    return "invalid_value"


def summarize_validation_errors(validation_errors: list[dict[str, str]]) -> str | None:
    messages: list[str] = []
    seen: set[str] = set()
    for item in validation_errors:
        message = str(item.get("message") or "").strip()
        if not message or message in seen:
            continue
        seen.add(message)
        messages.append(message)
    if not messages:
        return None
    if len(messages) == 1:
        return messages[0]
    return " ".join(messages[:3])


def validate_tool_input_against_schema(
    input_schema: dict[str, Any],
    input_data: Any,
    *,
    tool_name: str | None = None,
) -> list[dict[str, Any]]:
    if not input_schema:
        return []

    try:
        input_schema = sanitize_schema_dict(input_schema, tool_name=tool_name)
        validator_cls = validator_for(input_schema)
        validator_cls.check_schema(input_schema)
        validator = validator_cls(input_schema)
    except ToolSchemaValidationError as exc:
        return [
            {
                "code": "invalid_tool_schema",
                "path": exc.schema_path or "input",
                "message": str(exc),
            }
        ]
    except Exception as exc:
        return [
            {
                "code": "invalid_tool_schema",
                "path": "",
                "message": f"Invalid tool input schema: {exc}",
            }
        ]

    errors: list[ValidationError] = sorted(
        validator.iter_errors(input_data),
        key=lambda err: list(err.path),
    )
    normalized: list[dict[str, Any]] = []
    for err in errors:
        path = ".".join(str(part) for part in err.path)
        normalized.append(
            {
                "code": _validation_issue_code(err),
                "path": path,
                "message": _format_validation_message(err),
            }
        )
    return normalized


def validate_tool_input_schema(tool: Any, input_data: Any) -> list[dict[str, str]]:
    return validate_tool_input_against_schema(
        get_tool_input_schema(tool),
        input_data,
        tool_name=getattr(tool, "slug", None) or getattr(tool, "name", None),
    )
