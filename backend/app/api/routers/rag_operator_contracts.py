from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.api.routers.rag_pipelines import get_pipeline_context, sync_custom_operators
from app.db.postgres.session import get_db
from app.graph_authoring import rag_instance_contract, rag_node_spec
from app.db.postgres.models.rag import PipelineType
from app.rag.pipeline.registry import OperatorRegistry
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import ControlPlaneError
from app.services.control_plane.rag_admin_service import RagAdminService

router = APIRouter()


class OperatorSchemaRequest(BaseModel):
    pipeline_type: PipelineType
    operator_ids: list[str] = Field(default_factory=list)


@router.post("/operators/schema", response_model=Dict[str, Any])
async def get_operator_schemas(
    request: OperatorSchemaRequest,
    organization_id: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.catalog.read")),
    db: AsyncSession = Depends(get_db),
):
    organization, _user, _db = await get_pipeline_context(
        organization_id,
        current_user=context.get("user"),
        db=db,
        context=context,
    )
    if organization is None:
        registry = OperatorRegistry.get_instance()
        organization_id: Optional[str] = None
        operator_ids = [str(item).strip() for item in (request.operator_ids or []) if str(item).strip()]
        schemas: Dict[str, Dict[str, Any]] = {}
        unknown: list[str] = []
        normalized_pipeline_type = RagAdminService._normalize_pipeline_type(
            getattr(request.pipeline_type, "value", request.pipeline_type)
        )
        for operator_id in operator_ids:
            spec = registry.get(operator_id, organization_id=organization_id)
            if spec is None:
                unknown.append(operator_id)
                continue
            if not RagAdminService._operator_allowed_for_pipeline_type(spec, normalized_pipeline_type):
                unknown.append(operator_id)
                continue
            schemas[operator_id] = rag_node_spec(spec).model_dump(mode="json", exclude_none=True)
        return {"specs": schemas, "unknown": unknown, "instance_contract": rag_instance_contract()}
    try:
        result = await RagAdminService(db).operators_schema(
            ctx=ControlPlaneContext(
                organization_id=organization.id,
                user=context.get("user"),
                user_id=getattr(context.get("user"), "id", None),
                auth_token=context.get("auth_token"),
                scopes=tuple(context.get("scopes") or ()),
                is_service=bool(context.get("type") == "workload"),
            ),
            pipeline_type=getattr(request.pipeline_type, "value", request.pipeline_type),
            operator_ids=list(request.operator_ids or []),
        )
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    return {"specs": result["specs"], "unknown": [], "instance_contract": result["instance_contract"]}
