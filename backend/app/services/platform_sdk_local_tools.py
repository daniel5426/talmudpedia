from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from app.agent.execution.emitter import active_emitter
from app.db.postgres.engine import sessionmaker as get_session
from app.services.token_broker_service import TokenBrokerService
from app.services.tool_function_registry import register_tool_function
from app.system_artifacts.platform_sdk import handler as platform_sdk_handler


PLATFORM_SDK_LOCAL_FUNCTIONS: dict[str, str] = {
    "platform-rag": "platform_sdk_local_platform_rag",
    "platform-agents": "platform_sdk_local_platform_agents",
    "platform-assets": "platform_sdk_local_platform_assets",
    "platform-governance": "platform_sdk_local_platform_governance",
}


def _trace_safe_value(value: Any, *, max_string: int = 800, max_items: int = 12) -> Any:
    if callable(value):
        name = getattr(value, "__name__", value.__class__.__name__)
        return f"<callable:{name}>"
    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return value[:max_string] + "...[truncated]"
    if isinstance(value, dict):
        items = list(value.items())[:max_items]
        rendered = {str(key): _trace_safe_value(val, max_string=max_string, max_items=max_items) for key, val in items}
        if len(value) > max_items:
            rendered["__truncated_keys__"] = len(value) - max_items
        return rendered
    if isinstance(value, list):
        rendered = [_trace_safe_value(item, max_string=max_string, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items:
            rendered.append({"__truncated_items__": len(value) - max_items})
        return rendered
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return value


def _normalize_payload(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _parse_uuid(raw: Any) -> UUID | None:
    if raw in (None, ""):
        return None
    try:
        return UUID(str(raw))
    except Exception:
        return None


async def _mint_workload_token(grant_id: UUID, *, audience: str, scope_subset: list[str] | None = None) -> str | None:
    async with get_session() as db:
        token, _payload = await TokenBrokerService(db).mint_workload_token(
            grant_id=grant_id,
            audience=audience,
            scope_subset=scope_subset,
        )
        await db.commit()
        return token


async def _dispatch_platform_sdk_locally(*, tool_slug: str, payload: Any) -> dict[str, Any]:
    emitter = active_emitter.get()
    tool_payload = _normalize_payload(payload)
    payload_context = dict(tool_payload.get("context")) if isinstance(tool_payload.get("context"), dict) else {}
    grant_id = _parse_uuid(payload_context.get("grant_id") or tool_payload.get("grant_id"))

    async def mint_token(*, scope_subset: list[str] | None = None, audience: str = "talmudpedia-internal-api") -> str | None:
        if grant_id is None:
            return None
        return await _mint_workload_token(grant_id, audience=audience, scope_subset=scope_subset)

    runtime_context: dict[str, Any] = {
        "inputs": {
            **tool_payload,
            "tool_slug": tool_slug,
        },
        "tool_slug": tool_slug,
        **{
            key: value
            for key, value in payload_context.items()
            if key
            in {
                "tenant_id",
                "user_id",
                "initiator_user_id",
                "grant_id",
                "principal_id",
                "requested_scopes",
                "mode",
                "agent_id",
                "agent_slug",
                "surface",
            }
        },
    }
    if grant_id is not None:
        runtime_context["auth"] = {
            "grant_id": str(grant_id),
            "mint_token": mint_token,
        }
    if emitter:
        emitter.emit_internal_event(
            "platform_sdk_local.dispatch_prepared",
            {
                "tool_slug": tool_slug,
                "payload_preview": _trace_safe_value(tool_payload),
                "runtime_context_preview": _trace_safe_value(runtime_context),
            },
            category="platform_sdk_local",
        )

    result = await asyncio.to_thread(
        platform_sdk_handler.execute,
        {},
        {"tool_slug": tool_slug},
        runtime_context,
    )
    if emitter:
        emitter.emit_internal_event(
            "platform_sdk_local.dispatch_completed",
            {
                "tool_slug": tool_slug,
                "result_preview": _trace_safe_value(result),
            },
            category="platform_sdk_local",
        )
    return result


@register_tool_function(PLATFORM_SDK_LOCAL_FUNCTIONS["platform-rag"])
async def platform_sdk_local_platform_rag(payload: Any) -> dict[str, Any]:
    return await _dispatch_platform_sdk_locally(tool_slug="platform-rag", payload=payload)


@register_tool_function(PLATFORM_SDK_LOCAL_FUNCTIONS["platform-agents"])
async def platform_sdk_local_platform_agents(payload: Any) -> dict[str, Any]:
    return await _dispatch_platform_sdk_locally(tool_slug="platform-agents", payload=payload)


@register_tool_function(PLATFORM_SDK_LOCAL_FUNCTIONS["platform-assets"])
async def platform_sdk_local_platform_assets(payload: Any) -> dict[str, Any]:
    return await _dispatch_platform_sdk_locally(tool_slug="platform-assets", payload=payload)


@register_tool_function(PLATFORM_SDK_LOCAL_FUNCTIONS["platform-governance"])
async def platform_sdk_local_platform_governance(payload: Any) -> dict[str, Any]:
    return await _dispatch_platform_sdk_locally(tool_slug="platform-governance", payload=payload)
