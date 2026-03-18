from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.agents import get_agent_context
from app.api.dependencies import require_scopes
from app.db.postgres.session import get_db
from app.services.agent_service import AgentService
from app.services.tool_binding_service import ToolBindingService


router = APIRouter(prefix="/agents", tags=["agents"])


class ExportAgentToolRequest(BaseModel):
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)
    input_schema: dict[str, Any] | None = Field(default=None)


class ExportAgentToolResponse(BaseModel):
    tool_id: UUID
    tool_slug: str
    tool_name: str
    status: str


@router.post("/{agent_id}/export-tool", response_model=ExportAgentToolResponse)
async def export_agent_tool(
    agent_id: UUID,
    request: ExportAgentToolRequest,
    _: dict = Depends(require_scopes("agents.write")),
    agent_ctx: dict = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = UUID(str(agent_ctx["tenant_id"]))
    actor = agent_ctx.get("user")
    agent = await AgentService(db=db, tenant_id=tenant_id).get_agent(agent_id)
    tool = await ToolBindingService(db).export_agent_tool_binding(
        agent=agent,
        name=request.name,
        description=request.description,
        input_schema=request.input_schema,
        created_by=getattr(actor, "id", None),
    )
    await db.commit()
    await db.refresh(tool)
    return ExportAgentToolResponse(
        tool_id=tool.id,
        tool_slug=tool.slug,
        tool_name=tool.name,
        status=str(getattr(getattr(tool, "status", None), "value", getattr(tool, "status", ""))),
    )
