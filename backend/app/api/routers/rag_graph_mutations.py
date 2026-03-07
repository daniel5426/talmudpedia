from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.session import get_db
from app.services.rag_graph_mutation_service import RagGraphMutationService
from app.api.routers.rag_pipelines import (
    Action,
    get_pipeline_context,
    require_pipeline_permission,
)

router = APIRouter()


class GraphPatchRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)


class AttachKnowledgeStoreRequest(BaseModel):
    node_id: str
    knowledge_store_id: str


class SetPipelineNodeConfigRequest(BaseModel):
    node_id: str
    path: str
    value: Any


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
    pipeline_id: UUID,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.read")),
    db: AsyncSession = Depends(get_db),
):
    service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
    return await service.get_graph(pipeline_id)


@router.post("/visual-pipelines/{pipeline_id}/graph/validate-patch", response_model=Dict[str, Any])
async def validate_pipeline_graph_patch(
    pipeline_id: UUID,
    request: GraphPatchRequest,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
    return await service.validate_patch(pipeline_id, request.operations)


@router.post("/visual-pipelines/{pipeline_id}/graph/apply-patch", response_model=Dict[str, Any])
async def apply_pipeline_graph_patch(
    pipeline_id: UUID,
    request: GraphPatchRequest,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
    return await service.apply_patch(pipeline_id, request.operations)


@router.post("/visual-pipelines/{pipeline_id}/graph/attach-knowledge-store-to-node", response_model=Dict[str, Any])
async def attach_knowledge_store_to_node(
    pipeline_id: UUID,
    request: AttachKnowledgeStoreRequest,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
    return await service.attach_knowledge_store_to_node(
        pipeline_id,
        node_id=request.node_id,
        knowledge_store_id=request.knowledge_store_id,
    )


@router.post("/visual-pipelines/{pipeline_id}/graph/set-node-config", response_model=Dict[str, Any])
async def set_pipeline_node_config(
    pipeline_id: UUID,
    request: SetPipelineNodeConfigRequest,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    service = await _resolve_service(pipeline_id=pipeline_id, tenant_slug=tenant_slug, context=context, db=db)
    return await service.set_pipeline_node_config(
        pipeline_id,
        node_id=request.node_id,
        path=request.path,
        value=request.value,
    )
