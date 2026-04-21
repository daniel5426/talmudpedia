from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    require_organization_api_key_scopes,
)
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.db.postgres.session import get_db
from app.services.embedded_agent_runtime_service import (
    ensure_published_embed_agent,
    stream_embedded_agent,
)
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.runtime_surface import (
    RuntimeEventView,
    RuntimeSurfaceContext,
    RuntimeSurfaceService,
    RuntimeThreadOptions,
)
from app.services.thread_detail_service import serialize_thread_summary


router = APIRouter(prefix="/public/embed/agents", tags=["embedded-agents-public"])


class EmbeddedAgentChatStreamRequest(BaseModel):
    input: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    attachment_ids: list[UUID] = Field(default_factory=list)
    thread_id: UUID | None = None
    external_user_id: str = Field(min_length=1, max_length=255)
    external_session_id: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] | None = None
    client: dict[str, Any] | None = None


@router.post("/{agent_id}/chat/stream")
async def stream_embedded_agent_route(
    agent_id: UUID,
    request: EmbeddedAgentChatStreamRequest,
    principal: dict[str, Any] = Depends(require_organization_api_key_scopes("agents.embed")),
    db: AsyncSession = Depends(get_db),
):
    agent = await ensure_published_embed_agent(db=db, agent_id=agent_id)
    if str(agent.organization_id) != str(principal["organization_id"]):
        raise HTTPException(status_code=404, detail="Published agent not found")
    response = await stream_embedded_agent(
        db=db,
        agent=agent,
        api_key_principal=principal,
        input_text=request.input,
        messages=request.messages,
        attachment_ids=[str(item) for item in request.attachment_ids],
        thread_id=request.thread_id,
        external_user_id=request.external_user_id,
        external_session_id=request.external_session_id,
        metadata=request.metadata,
        client=request.client,
    )
    return response


@router.post("/{agent_id}/attachments/upload")
async def upload_embedded_agent_attachments(
    agent_id: UUID,
    files: list[UploadFile] = File(...),
    external_user_id: str = Form(...),
    external_session_id: str | None = Form(default=None),
    thread_id: UUID | None = Form(default=None),
    principal: dict[str, Any] = Depends(require_organization_api_key_scopes("agents.embed")),
    db: AsyncSession = Depends(get_db),
):
    agent = await ensure_published_embed_agent(db=db, agent_id=agent_id)
    if str(agent.organization_id) != str(principal["organization_id"]):
        raise HTTPException(status_code=404, detail="Published agent not found")
    owner = RuntimeAttachmentOwner(
        organization_id=agent.organization_id,
        surface=AgentThreadSurface.embedded_runtime,
        organization_api_key_id=UUID(str(principal["api_key_id"])),
        agent_id=agent.id,
        external_user_id=external_user_id,
        external_session_id=external_session_id,
        thread_id=thread_id,
    )
    attachment_service = RuntimeAttachmentService(db)
    if thread_id is not None:
        thread = await attachment_service.get_accessible_thread(owner=owner, thread_id=thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
    attachments = await attachment_service.upload_files(owner=owner, files=files)
    payload = {
        "items": [RuntimeAttachmentService.serialize_attachment(attachment) for attachment in attachments],
    }
    await db.commit()
    return payload


@router.get("/{agent_id}/threads")
async def list_embedded_agent_threads(
    agent_id: UUID,
    external_user_id: str = Query(..., min_length=1, max_length=255),
    external_session_id: str | None = Query(default=None, max_length=255),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    principal: dict[str, Any] = Depends(require_organization_api_key_scopes("agents.embed")),
    db: AsyncSession = Depends(get_db),
):
    agent = await ensure_published_embed_agent(db=db, agent_id=agent_id)
    if str(agent.organization_id) != str(principal["organization_id"]):
        raise HTTPException(status_code=404, detail="Published agent not found")

    items, total = await RuntimeSurfaceService(db).list_threads(
        scope=(
            RuntimeSurfaceContext(
                organization_id=agent.organization_id,
                surface=AgentThreadSurface.embedded_runtime,
                event_view=RuntimeEventView.public_safe,
                agent_id=agent.id,
                external_user_id=external_user_id,
                external_session_id=external_session_id,
            ).thread_scope(agent_id=agent.id)
        ),
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
    before_turn_index: int | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_subthreads: bool = Query(default=False),
    subthread_depth: int = Query(default=1, ge=1, le=5),
    subthread_turn_limit: int | None = Query(default=None, ge=1, le=100),
    subthread_child_limit: int = Query(default=20, ge=1, le=50),
    principal: dict[str, Any] = Depends(require_organization_api_key_scopes("agents.embed")),
    db: AsyncSession = Depends(get_db),
):
    agent = await ensure_published_embed_agent(db=db, agent_id=agent_id)
    if str(agent.organization_id) != str(principal["organization_id"]):
        raise HTTPException(status_code=404, detail="Published agent not found")

    return await RuntimeSurfaceService(db).get_thread_detail(
        scope=RuntimeSurfaceContext(
            organization_id=agent.organization_id,
            surface=AgentThreadSurface.embedded_runtime,
            event_view=RuntimeEventView.public_safe,
            agent_id=agent.id,
            external_user_id=external_user_id,
            external_session_id=external_session_id,
        ).thread_scope(agent_id=agent.id),
        thread_id=thread_id,
        options=RuntimeThreadOptions(
            before_turn_index=before_turn_index,
            limit=limit,
            include_subthreads=include_subthreads,
            subthread_depth=subthread_depth,
            subthread_turn_limit=subthread_turn_limit,
            subthread_child_limit=subthread_child_limit,
        ),
        event_view=RuntimeEventView.public_safe,
    )


@router.delete("/{agent_id}/threads/{thread_id}")
async def delete_embedded_agent_thread(
    agent_id: UUID,
    thread_id: UUID,
    external_user_id: str = Query(..., min_length=1, max_length=255),
    external_session_id: str | None = Query(default=None, max_length=255),
    principal: dict[str, Any] = Depends(require_organization_api_key_scopes("agents.embed")),
    db: AsyncSession = Depends(get_db),
):
    agent = await ensure_published_embed_agent(db=db, agent_id=agent_id)
    if str(agent.organization_id) != str(principal["organization_id"]):
        raise HTTPException(status_code=404, detail="Published agent not found")

    deleted = await RuntimeSurfaceService(db).delete_thread(
        scope=RuntimeSurfaceContext(
            organization_id=agent.organization_id,
            surface=AgentThreadSurface.embedded_runtime,
            event_view=RuntimeEventView.public_safe,
            agent_id=agent.id,
            external_user_id=external_user_id,
            external_session_id=external_session_id,
        ).thread_scope(agent_id=agent.id),
        thread_id=thread_id,
    )
    await db.commit()
    return {"deleted": bool(deleted)}
