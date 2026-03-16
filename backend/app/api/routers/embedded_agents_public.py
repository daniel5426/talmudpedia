from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    require_tenant_api_key_scopes,
)
from app.db.postgres.session import get_db
from app.services.embedded_agent_runtime_service import (
    ensure_published_embed_agent,
    serialize_thread_detail,
    serialize_thread_summary,
    stream_embedded_agent,
)
from app.services.thread_service import ThreadService


router = APIRouter(prefix="/public/embed/agents", tags=["embedded-agents-public"])


class EmbeddedAgentChatStreamRequest(BaseModel):
    input: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    thread_id: UUID | None = None
    external_user_id: str = Field(min_length=1, max_length=255)
    external_session_id: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] | None = None
    client: dict[str, Any] | None = None


@router.post("/{agent_id}/chat/stream")
async def stream_embedded_agent_route(
    agent_id: UUID,
    request: EmbeddedAgentChatStreamRequest,
    principal: dict[str, Any] = Depends(require_tenant_api_key_scopes("agents.embed")),
    db: AsyncSession = Depends(get_db),
):
    agent = await ensure_published_embed_agent(db=db, agent_id=agent_id)
    if str(agent.tenant_id) != str(principal["tenant_id"]):
        raise HTTPException(status_code=404, detail="Published agent not found")
    response = await stream_embedded_agent(
        db=db,
        agent=agent,
        api_key_principal=principal,
        input_text=request.input,
        messages=request.messages,
        thread_id=request.thread_id,
        external_user_id=request.external_user_id,
        external_session_id=request.external_session_id,
        metadata=request.metadata,
        client=request.client,
    )
    return response


@router.get("/{agent_id}/threads")
async def list_embedded_agent_threads(
    agent_id: UUID,
    external_user_id: str = Query(..., min_length=1, max_length=255),
    external_session_id: str | None = Query(default=None, max_length=255),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    principal: dict[str, Any] = Depends(require_tenant_api_key_scopes("agents.embed")),
    db: AsyncSession = Depends(get_db),
):
    agent = await ensure_published_embed_agent(db=db, agent_id=agent_id)
    if str(agent.tenant_id) != str(principal["tenant_id"]):
        raise HTTPException(status_code=404, detail="Published agent not found")

    items, total = await ThreadService(db).list_threads(
        tenant_id=agent.tenant_id,
        agent_id=agent.id,
        external_user_id=external_user_id,
        external_session_id=external_session_id,
        skip=skip,
        limit=limit,
    )
    await db.commit()
    return {"items": [serialize_thread_summary(item) for item in items], "total": total}


@router.get("/{agent_id}/threads/{thread_id}")
async def get_embedded_agent_thread(
    agent_id: UUID,
    thread_id: UUID,
    external_user_id: str = Query(..., min_length=1, max_length=255),
    external_session_id: str | None = Query(default=None, max_length=255),
    principal: dict[str, Any] = Depends(require_tenant_api_key_scopes("agents.embed")),
    db: AsyncSession = Depends(get_db),
):
    agent = await ensure_published_embed_agent(db=db, agent_id=agent_id)
    if str(agent.tenant_id) != str(principal["tenant_id"]):
        raise HTTPException(status_code=404, detail="Published agent not found")

    thread = await ThreadService(db).get_thread_with_turns(
        tenant_id=agent.tenant_id,
        thread_id=thread_id,
        agent_id=agent.id,
        external_user_id=external_user_id,
        external_session_id=external_session_id,
    )
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    await db.commit()
    return serialize_thread_detail(thread)
