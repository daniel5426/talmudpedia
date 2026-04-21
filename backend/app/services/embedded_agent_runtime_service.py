from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.services.runtime_surface import (
    RuntimeChatRequest,
    RuntimeEventView,
    RuntimeStreamOptions,
    RuntimeSurfaceContext,
    RuntimeSurfaceService,
)
from app.services.usage_quota_service import QuotaExceededError


def _stream_v2_enforced() -> bool:
    raw = (os.getenv("STREAM_V2_ENFORCED") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


async def ensure_published_embed_agent(*, db: AsyncSession, agent_id: UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.status != AgentStatus.published:
        raise HTTPException(status_code=404, detail="Published agent not found")
    return agent


async def stream_embedded_agent(
    *,
    db: AsyncSession,
    agent: Agent,
    api_key_principal: dict[str, Any],
    input_text: str | None,
    messages: list[dict[str, Any]],
    attachment_ids: list[str] | None,
    thread_id: UUID | None,
    external_user_id: str,
    external_session_id: str | None,
    metadata: dict[str, Any] | None,
    client: dict[str, Any] | None,
) -> StreamingResponse | JSONResponse:
    try:
        return await RuntimeSurfaceService(db).stream_chat(
            agent_id=agent.id,
            surface_context=RuntimeSurfaceContext(
                organization_id=agent.organization_id,
                surface=AgentThreadSurface.embedded_runtime,
                event_view=RuntimeEventView.public_safe,
                agent_id=agent.id,
                external_user_id=external_user_id,
                external_session_id=external_session_id,
                context_defaults={
                    "surface": "embedded_agent_runtime",
                    "external_user_id": external_user_id,
                    "external_session_id": external_session_id,
                    "organization_api_key_id": api_key_principal["api_key_id"],
                    "organization_api_key_name": api_key_principal.get("name"),
                    "organization_api_key_prefix": api_key_principal.get("key_prefix"),
                    "embed_metadata": dict(metadata or {}),
                    "embed_client": dict(client or {}),
                },
            ),
            request=RuntimeChatRequest(
                input=input_text,
                messages=list(messages or []),
                attachment_ids=list(attachment_ids or []),
                thread_id=thread_id,
                client=dict(client or {}),
            ),
            options=RuntimeStreamOptions(
                execution_mode=ExecutionMode.PRODUCTION,
                preload_thread_messages=True,
                stream_v2_enforced=_stream_v2_enforced(),
                padding_bytes=2048,
                include_content_encoding_identity=True,
            ),
        )
    except QuotaExceededError as exc:
        return JSONResponse(status_code=429, content=exc.to_payload())
