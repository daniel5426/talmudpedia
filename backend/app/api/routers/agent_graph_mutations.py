from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_scopes
from app.api.routers.agents import get_agent_context
from app.db.postgres.session import get_db
from app.services.agent_service import AgentGraphValidationError, AgentNotFoundError, AgentServiceError
from app.services.agent_graph_mutation_service import AgentGraphMutationService
from app.services.graph_mutation_service import GraphMutationError

router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger(__name__)


class GraphPatchRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)


class GraphAnalysisRequest(BaseModel):
    graph_definition: dict[str, Any] = Field(default_factory=dict)


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


def _request_id(request: Request) -> str:
    return str(request.headers.get("X-Request-ID") or "").strip()


def _raise_agent_graph_http_error(
    *,
    request: Request,
    agent_id: UUID,
    operation: str,
    exc: Exception,
) -> None:
    request_id = _request_id(request)
    phase = str(getattr(exc, "graph_mutation_phase", "") or "").strip() or None

    if isinstance(exc, HTTPException):
        raise exc

    if isinstance(exc, AgentNotFoundError):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": exc.message,
                "request_id": request_id,
                "operation": operation,
            },
        ) from exc

    if isinstance(exc, AgentGraphValidationError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Graph write rejected",
                "errors": exc.errors,
                "request_id": request_id,
                "operation": operation,
                "phase": phase,
            },
        ) from exc

    if isinstance(exc, GraphMutationError):
        errors = list(exc.errors or [])
        first = errors[0] if errors else {}
        status_code = 404 if str(first.get("code") or "").endswith("_NOT_FOUND") else 422
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": str(first.get("code") or "GRAPH_MUTATION_ERROR"),
                "message": str(first.get("message") or "Graph mutation failed"),
                "errors": errors,
                "request_id": request_id,
                "operation": operation,
                "phase": phase,
            },
        ) from exc

    if isinstance(exc, AgentServiceError):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "AGENT_SERVICE_ERROR",
                "message": exc.message,
                "request_id": request_id,
                "operation": operation,
                "phase": phase,
            },
        ) from exc

    logger.exception(
        "Unhandled agent graph mutation error",
        extra={
            "agent_id": str(agent_id),
            "operation": operation,
            "request_id": request_id,
            "phase": phase,
            "error_class": exc.__class__.__name__,
        },
    )
    raise HTTPException(
        status_code=500,
        detail={
            "code": "GRAPH_MUTATION_INTERNAL_ERROR",
            "message": "Agent graph mutation failed due to an internal server error",
            "error_class": exc.__class__.__name__,
            "error_message": str(exc),
            "request_id": request_id,
            "operation": operation,
            "phase": phase,
            "resource_type": "agent",
            "resource_id": str(agent_id),
        },
    ) from exc


@router.get("/{agent_id}/graph", response_model=Dict[str, Any])
async def get_agent_graph(
    request: Request,
    agent_id: UUID,
    _: Dict[str, Any] = Depends(require_scopes("agents.read")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(
        db=db,
        organization_id=context["organization_id"],
        project_id=context.get("project_id"),
    )
    try:
        return await service.get_graph(agent_id)
    except Exception as exc:
        _raise_agent_graph_http_error(request=request, agent_id=agent_id, operation="agents.graph.get", exc=exc)


@router.post("/{agent_id}/graph/validate-patch", response_model=Dict[str, Any])
async def validate_agent_graph_patch(
    http_request: Request,
    agent_id: UUID,
    payload: GraphPatchRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(
        db=db,
        organization_id=context["organization_id"],
        project_id=context.get("project_id"),
    )
    try:
        return await service.validate_patch(agent_id, payload.operations)
    except Exception as exc:
        _raise_agent_graph_http_error(
            request=http_request,
            agent_id=agent_id,
            operation="agents.graph.validate_patch",
            exc=exc,
        )


@router.post("/{agent_id}/graph/analyze", response_model=Dict[str, Any])
async def analyze_agent_graph(
    request: Request,
    agent_id: UUID,
    payload: GraphAnalysisRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.read")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(
        db=db,
        organization_id=context["organization_id"],
        project_id=context.get("project_id"),
    )
    try:
        return await service.analyze_graph(agent_id, graph_definition=payload.graph_definition)
    except Exception as exc:
        _raise_agent_graph_http_error(
            request=request,
            agent_id=agent_id,
            operation="agents.graph.analyze",
            exc=exc,
        )


@router.post("/{agent_id}/graph/apply-patch", response_model=Dict[str, Any])
async def apply_agent_graph_patch(
    request: Request,
    agent_id: UUID,
    payload: GraphPatchRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(
        db=db,
        organization_id=context["organization_id"],
        project_id=context.get("project_id"),
    )
    try:
        return await service.apply_patch(
            agent_id,
            payload.operations,
            user_id=context["user"].id if context.get("user") else None,
        )
    except Exception as exc:
        _raise_agent_graph_http_error(
            request=request,
            agent_id=agent_id,
            operation="agents.graph.apply_patch",
            exc=exc,
        )


@router.post("/{agent_id}/graph/add-tool-to-agent-node", response_model=Dict[str, Any])
async def add_tool_to_agent_node(
    request: Request,
    agent_id: UUID,
    payload: AddToolRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(
        db=db,
        organization_id=context["organization_id"],
        project_id=context.get("project_id"),
    )
    try:
        return await service.add_tool_to_agent_node(
            agent_id,
            node_id=payload.node_id,
            tool_id=payload.tool_id,
            user_id=context["user"].id if context.get("user") else None,
        )
    except Exception as exc:
        _raise_agent_graph_http_error(
            request=request,
            agent_id=agent_id,
            operation="agents.graph.add_tool_to_agent_node",
            exc=exc,
        )


@router.post("/{agent_id}/graph/remove-tool-from-agent-node", response_model=Dict[str, Any])
async def remove_tool_from_agent_node(
    request: Request,
    agent_id: UUID,
    payload: RemoveToolRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(
        db=db,
        organization_id=context["organization_id"],
        project_id=context.get("project_id"),
    )
    try:
        return await service.remove_tool_from_agent_node(
            agent_id,
            node_id=payload.node_id,
            tool_id=payload.tool_id,
            user_id=context["user"].id if context.get("user") else None,
        )
    except Exception as exc:
        _raise_agent_graph_http_error(
            request=request,
            agent_id=agent_id,
            operation="agents.graph.remove_tool_from_agent_node",
            exc=exc,
        )


@router.post("/{agent_id}/graph/set-agent-model", response_model=Dict[str, Any])
async def set_agent_model(
    request: Request,
    agent_id: UUID,
    payload: SetModelRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(
        db=db,
        organization_id=context["organization_id"],
        project_id=context.get("project_id"),
    )
    try:
        return await service.set_agent_model(
            agent_id,
            node_id=payload.node_id,
            model_id=payload.model_id,
            user_id=context["user"].id if context.get("user") else None,
        )
    except Exception as exc:
        _raise_agent_graph_http_error(
            request=request,
            agent_id=agent_id,
            operation="agents.graph.set_agent_model",
            exc=exc,
        )


@router.post("/{agent_id}/graph/set-agent-instructions", response_model=Dict[str, Any])
async def set_agent_instructions(
    request: Request,
    agent_id: UUID,
    payload: SetInstructionsRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    service = AgentGraphMutationService(
        db=db,
        organization_id=context["organization_id"],
        project_id=context.get("project_id"),
    )
    try:
        return await service.set_agent_instructions(
            agent_id,
            node_id=payload.node_id,
            instructions=payload.instructions,
            user_id=context["user"].id if context.get("user") else None,
        )
    except Exception as exc:
        _raise_agent_graph_http_error(
            request=request,
            agent_id=agent_id,
            operation="agents.graph.set_agent_instructions",
            exc=exc,
        )
