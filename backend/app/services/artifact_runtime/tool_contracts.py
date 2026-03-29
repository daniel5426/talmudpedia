from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from app.api.schemas.artifacts import ToolArtifactContract


class ToolContractValidationError(ValueError):
    pass


def validate_tool_contract(
    value: Any,
    *,
    source: str = "tool_contract",
    allow_legacy_wrapper: bool = False,
) -> dict[str, Any]:
    candidate = deepcopy(value)
    if allow_legacy_wrapper and _is_wrapped_tool_contract(candidate):
        candidate = deepcopy(candidate["tool_contract"])
    elif _is_wrapped_tool_contract(candidate):
        raise ToolContractValidationError(
            f"{source} must be the inner tool contract object, not wrapped in an outer 'tool_contract' field"
        )
    candidate = _normalize_tool_contract_nested_objects(candidate, source=source)
    try:
        return ToolArtifactContract.model_validate(candidate).model_dump()
    except ValidationError as exc:
        raise ToolContractValidationError(f"{source} is invalid: {_validation_error_message(exc)}") from exc


def parse_tool_contract_json(
    value: Any,
    *,
    source: str = "tool_contract",
    allow_legacy_wrapper: bool = False,
) -> dict[str, Any]:
    return validate_tool_contract(
        _parse_json_object(value, source=source),
        source=source,
        allow_legacy_wrapper=allow_legacy_wrapper,
    )
def _is_wrapped_tool_contract(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("tool_contract"), dict)


def _parse_json_object(value: Any, *, source: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    if value is None:
        raise ValueError(f"{source} must be a JSON object")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{source} must be a JSON object")
    try:
        parsed = json.loads(text)
    except Exception as exc:
        raise ValueError(f"{source} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{source} must be a JSON object")
    return deepcopy(parsed)


def _normalize_tool_contract_nested_objects(value: Any, *, source: str) -> Any:
    if not isinstance(value, dict):
        return value
    normalized = deepcopy(value)
    for field_name in ("input_schema", "output_schema", "tool_ui"):
        field_value = normalized.get(field_name)
        if isinstance(field_value, str):
            normalized[field_name] = _parse_json_object(field_value, source=f"{source}.{field_name}")
    return normalized


def _validation_error_message(exc: ValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(item) for item in first.get("loc") or [])
    message = str(first.get("msg") or "validation failed")
    if location:
        return f"{location}: {message}"
    return message
