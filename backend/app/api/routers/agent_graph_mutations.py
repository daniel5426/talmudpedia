from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_scopes
from app.api.routers.agents import get_agent_context
from app.db.postgres.session import get_db
from app.services.agent_graph_mutation_service import AgentGraphMutationService

router = APIRouter(prefix="/agents", tags=["agents"])


class GraphPatchRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)


class AddToolRequest(BaseModel):
    node_id: str
    tool_id: str


class RemoveToolRequest(BaseModel):
    node_id: str
    tool_id: str


class SetModelRequest(BaseModel):
    node_id: str
    model_id: str


class SetInstructionsRequest(BaseModel):
    node_id: str
    instructions: str


@router.get("/{agent_id}/graph", response_model=Dict[str, Any])
async def get_agent_graph(
    agent_id: UUID,
    _: Dict[str, Any] = Depends(require_scopes("agents.read")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(db=db, tenant_id=context["tenant_id"])
    return await service.get_graph(agent_id)


@router.post("/{agent_id}/graph/validate-patch", response_model=Dict[str, Any])
async def validate_agent_graph_patch(
    agent_id: UUID,
    request: GraphPatchRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(db=db, tenant_id=context["tenant_id"])
    return await service.validate_patch(agent_id, request.operations)


@router.post("/{agent_id}/graph/apply-patch", response_model=Dict[str, Any])
async def apply_agent_graph_patch(
    agent_id: UUID,
    request: GraphPatchRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(db=db, tenant_id=context["tenant_id"])
    return await service.apply_patch(
        agent_id,
        request.operations,
        user_id=context["user"].id if context.get("user") else None,
    )


@router.post("/{agent_id}/graph/add-tool-to-agent-node", response_model=Dict[str, Any])
async def add_tool_to_agent_node(
    agent_id: UUID,
    request: AddToolRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(db=db, tenant_id=context["tenant_id"])
    return await service.add_tool_to_agent_node(
        agent_id,
        node_id=request.node_id,
        tool_id=request.tool_id,
        user_id=context["user"].id if context.get("user") else None,
    )


@router.post("/{agent_id}/graph/remove-tool-from-agent-node", response_model=Dict[str, Any])
async def remove_tool_from_agent_node(
    agent_id: UUID,
    request: RemoveToolRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(db=db, tenant_id=context["tenant_id"])
    return await service.remove_tool_from_agent_node(
        agent_id,
        node_id=request.node_id,
        tool_id=request.tool_id,
        user_id=context["user"].id if context.get("user") else None,
    )


@router.post("/{agent_id}/graph/set-agent-model", response_model=Dict[str, Any])
async def set_agent_model(
    agent_id: UUID,
    request: SetModelRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(db=db, tenant_id=context["tenant_id"])
    return await service.set_agent_model(
        agent_id,
        node_id=request.node_id,
        model_id=request.model_id,
        user_id=context["user"].id if context.get("user") else None,
    )


@router.post("/{agent_id}/graph/set-agent-instructions", response_model=Dict[str, Any])
async def set_agent_instructions(
    agent_id: UUID,
    request: SetInstructionsRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(db=db, tenant_id=context["tenant_id"])
    return await service.set_agent_instructions(
        agent_id,
        node_id=request.node_id,
        instructions=request.instructions,
        user_id=context["user"].id if context.get("user") else None,
    )
