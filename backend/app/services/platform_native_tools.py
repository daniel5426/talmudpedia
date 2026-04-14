from __future__ import annotations

from app.db.postgres.engine import sessionmaker as get_session
from app.services.platform_native import ACTION_HANDLERS, dispatch_native_platform_tool
from app.services.tool_function_registry import register_tool_function


PLATFORM_NATIVE_FUNCTIONS: dict[str, str] = {
    "platform-rag": "platform_native_platform_rag",
    "platform-agents": "platform_native_platform_agents",
    "platform-assets": "platform_native_platform_assets",
    "platform-governance": "platform_native_platform_governance",
}

_ACTION_HANDLERS = ACTION_HANDLERS


async def _dispatch(tool_slug: str, payload: dict) -> dict:
    async with get_session() as db:
        return await dispatch_native_platform_tool(
            db=db,
            tool_slug=tool_slug,
            inputs=dict(payload or {}),
            handlers=_ACTION_HANDLERS,
        )


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
