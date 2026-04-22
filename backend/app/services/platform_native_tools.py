from __future__ import annotations

from app.db.postgres.engine import sessionmaker as get_session
from app.services.platform_architect_contracts import (
    PLATFORM_ARCHITECT_ACTION_DOMAIN_BY_ID,
    PLATFORM_ARCHITECT_CANONICAL_ACTION_TOOL_KEYS,
)
from app.services.platform_native import ACTION_HANDLERS, dispatch_native_platform_tool
from app.services.tool_function_registry import register_tool_function


PLATFORM_NATIVE_FUNCTIONS: dict[str, str] = {
    "platform-rag": "platform_native_platform_rag",
    "platform-agents": "platform_native_platform_agents",
    "platform-assets": "platform_native_platform_assets",
    "platform-governance": "platform_native_platform_governance",
}
PLATFORM_ACTION_FUNCTIONS: dict[str, str] = {}

_GENERIC_ACTION_CONTROL_FIELDS = frozenset(
    {
        "dry_run",
        "validate_only",
        "idempotency_key",
        "request_metadata",
        "__tool_runtime_context__",
    }
)

_ACTION_HANDLERS = ACTION_HANDLERS


async def _dispatch(builtin_key: str, payload: dict) -> dict:
    async with get_session() as db:
        return await dispatch_native_platform_tool(
            db=db,
            builtin_key=builtin_key,
            inputs=dict(payload or {}),
            handlers=_ACTION_HANDLERS,
        )


def _action_function_name(action_id: str) -> str:
    return f"platform_action_{action_id.replace('.', '_')}"


def _build_action_dispatch_payload(action_id: str, raw_payload: dict | None) -> dict:
    payload = dict(raw_payload or {})
    runtime_context = payload.pop("__tool_runtime_context__", None)
    dispatch_payload = {
        "action": action_id,
        "payload": {
            key: value
            for key, value in payload.items()
            if key not in _GENERIC_ACTION_CONTROL_FIELDS
        },
    }
    for field in ("dry_run", "validate_only", "idempotency_key", "request_metadata"):
        if field in payload:
            dispatch_payload[field] = payload[field]
    if runtime_context is not None:
        dispatch_payload["__tool_runtime_context__"] = runtime_context
    return dispatch_payload


@register_tool_function("platform_native_platform_rag")
async def platform_native_platform_rag(payload: dict) -> dict:
    return await _dispatch("platform-rag", payload)


@register_tool_function("platform_native_platform_agents")
async def platform_native_platform_agents(payload: dict) -> dict:
    return await _dispatch("platform-agents", payload)


@register_tool_function("platform_native_platform_assets")
async def platform_native_platform_assets(payload: dict) -> dict:
    return await _dispatch("platform-assets", payload)


@register_tool_function("platform_native_platform_governance")
async def platform_native_platform_governance(payload: dict) -> dict:
    return await _dispatch("platform-governance", payload)


def _register_platform_action_wrappers() -> None:
    for action_id in PLATFORM_ARCHITECT_CANONICAL_ACTION_TOOL_KEYS:
        function_name = _action_function_name(action_id)
        PLATFORM_ACTION_FUNCTIONS[action_id] = function_name
        if function_name in globals():
            continue

        builtin_key = PLATFORM_ARCHITECT_ACTION_DOMAIN_BY_ID[action_id]

        async def _tool(payload: dict, *, _action_id: str = action_id, _builtin_key: str = builtin_key) -> dict:
            return await _dispatch(_builtin_key, _build_action_dispatch_payload(_action_id, payload))

        _tool.__name__ = function_name
        _tool.__qualname__ = function_name
        globals()[function_name] = register_tool_function(function_name)(_tool)


_register_platform_action_wrappers()
