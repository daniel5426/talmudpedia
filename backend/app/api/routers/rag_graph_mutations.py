from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.session import get_db
from app.services.rag_graph_mutation_service import RagGraphMutationService
from app.services.graph_mutation_service import GraphMutationError
from app.api.routers.rag_pipelines import (
    Action,
    get_pipeline_context,
    require_pipeline_permission,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class GraphPatchRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)


class AttachKnowledgeStoreRequest(BaseModel):
    node_id: str
    knowledge_store_id: str


class SetPipelineNodeConfigRequest(BaseModel):
    node_id: str
    path: str
    value: Any


def _request_id(request: Request) -> str:
    return str(request.headers.get("X-Request-ID") or "").strip()


def _raise_pipeline_graph_http_error(
    *,
    request: Request,
    pipeline_id: UUID,
    operation: str,
    exc: Exception,
) -> None:
    request_id = _request_id(request)
    phase = str(getattr(exc, "graph_mutation_phase", "") or "").strip() or None

    if isinstance(exc, HTTPException):
        raise exc

    if isinstance(exc, GraphMutationError):
        errors = list(exc.errors or [])
        first = errors[0] if errors else {}
        code = str(first.get("code") or "GRAPH_MUTATION_ERROR")
        status_code = 404 if code.endswith("_NOT_FOUND") else 422
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": code,
                "message": str(first.get("message") or "Graph mutation failed"),
                "errors": errors,
                "request_id": request_id,
                "operation": operation,
                "phase": phase,
            },
        ) from exc

    logger.exception(
        "Unhandled RAG graph mutation error",
        extra={
            "pipeline_id": str(pipeline_id),
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
            "message": "RAG graph mutation failed due to an internal server error",
            "error_class": exc.__class__.__name__,
            "error_message": str(exc),
            "request_id": request_id,
            "operation": operation,
            "phase": phase,
            "resource_type": "rag_pipeline",
            "resource_id": str(pipeline_id),
        },
    ) from exc


async def _resolve_service(
    *,
    pipeline_id: UUID,
    tenant_slug: Optional[str],
    context: Dict[str, Any],
    db: AsyncSession,
) -> RagGraphMutationService:
    tenant, user, _db = await get_pipeline_context(
        tenant_slug,
        current_user=context.get("user"),
        db=db,
        context=context,
    )
    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")
    if not await require_pipeline_permission(tenant, user, Action.WRITE, pipeline_id=pipeline_id, db=db):
        raise HTTPException(status_code=403, detail="Permission denied")
    return RagGraphMutationService(db=db, tenant_id=tenant.id)


@router.get("/visual-pipelines/{pipeline_id}/graph", response_model=Dict[str, Any])
async def get_pipeline_graph(
    request: Request,
    pipeline_id: UUID,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
        return await service.get_graph(pipeline_id)
    except Exception as exc:
        _raise_pipeline_graph_http_error(
            request=request,
            pipeline_id=pipeline_id,
            operation="rag.graph.get",
            exc=exc,
        )


@router.post("/visual-pipelines/{pipeline_id}/graph/validate-patch", response_model=Dict[str, Any])
async def validate_pipeline_graph_patch(
    request: Request,
    pipeline_id: UUID,
    payload: GraphPatchRequest,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
        return await service.validate_patch(pipeline_id, payload.operations)
    except Exception as exc:
        _raise_pipeline_graph_http_error(
            request=request,
            pipeline_id=pipeline_id,
            operation="rag.graph.validate_patch",
            exc=exc,
        )


@router.post("/visual-pipelines/{pipeline_id}/graph/apply-patch", response_model=Dict[str, Any])
async def apply_pipeline_graph_patch(
    request: Request,
    pipeline_id: UUID,
    payload: GraphPatchRequest,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
        return await service.apply_patch(pipeline_id, payload.operations)
    except Exception as exc:
        _raise_pipeline_graph_http_error(
            request=request,
            pipeline_id=pipeline_id,
            operation="rag.graph.apply_patch",
            exc=exc,
        )


@router.post("/visual-pipelines/{pipeline_id}/graph/attach-knowledge-store-to-node", response_model=Dict[str, Any])
async def attach_knowledge_store_to_node(
    request: Request,
    pipeline_id: UUID,
    payload: AttachKnowledgeStoreRequest,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
        return await service.attach_knowledge_store_to_node(
            pipeline_id,
            node_id=payload.node_id,
            knowledge_store_id=payload.knowledge_store_id,
        )
    except Exception as exc:
        _raise_pipeline_graph_http_error(
            request=request,
            pipeline_id=pipeline_id,
            operation="rag.graph.attach_knowledge_store_to_node",
            exc=exc,
        )


@router.post("/visual-pipelines/{pipeline_id}/graph/set-node-config", response_model=Dict[str, Any])
async def set_pipeline_node_config(
    request: Request,
    pipeline_id: UUID,
    payload: SetPipelineNodeConfigRequest,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
        return await service.set_pipeline_node_config(
            pipeline_id,
            node_id=payload.node_id,
            path=payload.path,
            value=payload.value,
        )
    except Exception as exc:
        _raise_pipeline_graph_http_error(
            request=request,
            pipeline_id=pipeline_id,
            operation="rag.graph.set_pipeline_node_config",
            exc=exc,
        )
