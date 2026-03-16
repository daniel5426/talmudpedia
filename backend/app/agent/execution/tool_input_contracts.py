from __future__ import annotations

import json
import re
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
                "message": _format_validation_message(err),
            }
        )
    return normalized
