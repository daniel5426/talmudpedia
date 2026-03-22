"""
Agents API Router - Thin dispatch layer for agent endpoints.

Routers should only: Validate, Authenticate, Dispatch.
All business logic lives in AgentService.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import json
import logging
import os
from pydantic import BaseModel, Field

from app.db.postgres.session import get_db
from app.api.dependencies import get_current_principal, require_scopes, ensure_sensitive_action_approved
from app.db.postgres.models.identity import OrgMembership
from app.core.scope_registry import is_platform_admin_role
from typing import Dict, Any
from fastapi import Request

from app.services.agent_service import (
    AgentService,
    CreateAgentData,
    UpdateAgentData,
    ExecuteAgentData,
    AgentServiceError,
    AgentNotFoundError,
    AgentSlugExistsError,
    AgentGraphValidationError,
    AgentPublishedError,
    AgentNotPublishedError,
)
from app.services.usage_quota_service import QuotaExceededError
from app.agent.graph.contracts import contract_fields_from_schema, schema_to_value_type
from app.agent.execution.stream_contract_v2 import (
    build_stream_v2_event,
    normalize_filtered_event_to_v2,
)
from app.api.schemas.agents import (
    CreateAgentRequest,
    UpdateAgentRequest,
    GraphDefinitionSchema,
    AgentResponse,
    AgentListResponse,
    ExecuteAgentRequest,
    ExecuteAgentResponse,
    CancelRunRequest,
)
from app.db.postgres.models.agents import Agent, AgentRun
from sqlalchemy import select
from typing import Optional
from datetime import datetime
from app.db.postgres.models.agent_threads import AgentThreadSurface, AgentThreadTurnStatus
from app.db.postgres.models.agents import RunStatus
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.thread_service import ThreadService


router = APIRouter(prefix="/agents", tags=["agents"])


class NodeSchemaRequest(BaseModel):
    node_types: list[str] = Field(default_factory=list)


def _stream_v2_enforced() -> bool:
    raw = (os.getenv("STREAM_V2_ENFORCED") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _optional_uuid(value: Any) -> Optional[UUID]:
    if value in {None, ""}:
        return None
    try:
        return UUID(str(value))
    except Exception:
        return None


# =============================================================================
# Helpers
# =============================================================================

async def get_agent_context(
    request: Request,
    context: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns a context dict with 'user' and 'tenant_id'.
    Users can manage agents if they are System Admins OR have an Org role.
    """
    token = context.get("auth_token")
    if context.get("type") == "workload":
        tenant_id = context.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        return {
            "user": None,
            "tenant_id": tenant_id,
            "auth_token": token,
            "is_service": True,
            "principal_id": context.get("principal_id"),
            "grant_id": context.get("grant_id"),
            "initiator_user_id": context.get("initiator_user_id"),
            "scopes": context.get("scopes", []),
        }

    current_user = context.get("user")
    if current_user is None:
        raise HTTPException(status_code=403, detail="Not authorized to manage agents")

    # Prefer explicit tenant header so multi-tenant users can target the selected tenant.
    header_tenant = request.headers.get("X-Tenant-ID")
    resolved_tenant: UUID | None = None
    if header_tenant:
        try:
            header_tenant_uuid = UUID(str(header_tenant))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid X-Tenant-ID header")
        resolved_tenant = header_tenant_uuid
    else:
        tenant_id = context.get("tenant_id")
        if tenant_id is None:
            raise HTTPException(status_code=403, detail="Tenant context required")
        try:
            resolved_tenant = UUID(str(tenant_id))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid tenant context")

    membership_res = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == current_user.id,
            OrgMembership.tenant_id == resolved_tenant,
        ).limit(1)
    )
    membership = membership_res.scalar_one_or_none()
    if membership is None and not is_platform_admin_role(getattr(current_user, "role", None)):
        raise HTTPException(status_code=403, detail="Not a member of the requested tenant")

    return {
        "user": current_user,
        "tenant_id": resolved_tenant,
        "auth_token": token,
        "is_service": False,
        "scopes": context.get("scopes", []),
    }


def agent_to_response(agent, compact: bool = False) -> AgentResponse:
    """Convert Agent model to response."""
    workload_scope_profile = "default_agent_run" if compact else (getattr(agent, "workload_scope_profile", "default_agent_run") or "default_agent_run")
    workload_scope_overrides = [] if compact else list(getattr(agent, "workload_scope_overrides", []) or [])

    return AgentResponse(
        id=agent.id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        slug=agent.slug,
        description=agent.description,
        graph_definition={"nodes": [], "edges": []} if compact else (agent.graph_definition or {"nodes": [], "edges": []}),
        memory_config={} if compact else (agent.memory_config or {}),
        execution_constraints={} if compact else (agent.execution_constraints or {}),
        version=agent.version,
        status=agent.status.value if hasattr(agent.status, "value") else (agent.status or "draft"),

        is_active=agent.is_active,
        is_public=agent.is_public,
        show_in_playground=bool(getattr(agent, "show_in_playground", True)),
        workload_scope_profile=workload_scope_profile,
        workload_scope_overrides=workload_scope_overrides,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        published_at=agent.published_at,
    )


def handle_service_error(e: AgentServiceError):
    """Map service errors to HTTP responses."""
    if isinstance(e, AgentNotFoundError):
        raise HTTPException(status_code=404, detail=e.message)
    if isinstance(e, AgentGraphValidationError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Graph validation failed",
                "errors": e.errors,
            },
        )
    if isinstance(e, AgentSlugExistsError):
        raise HTTPException(status_code=400, detail=e.message)
    if isinstance(e, AgentPublishedError):
        raise HTTPException(status_code=400, detail=e.message)
    if isinstance(e, AgentNotPublishedError):
        raise HTTPException(status_code=400, detail=e.message)
    raise HTTPException(status_code=500, detail=e.message)



# =============================================================================
# Catalog Endpoint
# =============================================================================

def _artifact_field_type(json_type: str) -> str:
    mapping = {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "array": "text",
        "object": "text",
    }
    return mapping.get(str(json_type or "").strip().lower(), "string")


def _artifact_config_fields_from_schema(config_schema: dict[str, Any]) -> list[dict[str, Any]]:
    properties = config_schema.get("properties") if isinstance(config_schema.get("properties"), dict) else {}
    required = set(config_schema.get("required") or []) if isinstance(config_schema.get("required"), list) else set()
    fields: list[dict[str, Any]] = []
    for key, value in properties.items():
        if not isinstance(value, dict):
            value = {}
        field: dict[str, Any] = {
            "name": key,
            "label": str(value.get("title") or key),
            "fieldType": _artifact_field_type(value.get("type")),
            "required": key in required,
            "description": value.get("description"),
        }
        enum_values = value.get("enum")
        if isinstance(enum_values, list) and enum_values:
            field["fieldType"] = "select"
            field["options"] = [{"value": str(item), "label": str(item)} for item in enum_values]
        if "default" in value:
            field["default"] = value.get("default")
        fields.append(field)
    return fields


def _artifact_input_specs(input_schema: dict[str, Any], node_ui: dict[str, Any]) -> list[dict[str, Any]]:
    properties = input_schema.get("properties") if isinstance(input_schema.get("properties"), dict) else {}
    required = set(input_schema.get("required") or []) if isinstance(input_schema.get("required"), list) else set()
    ui_inputs = node_ui.get("inputs") if isinstance(node_ui.get("inputs"), list) else []
    input_labels = {
        str(item.get("name") or "").strip(): str(item.get("label") or item.get("title") or item.get("name") or "").strip()
        for item in ui_inputs
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    specs: list[dict[str, Any]] = []
    for key, value in properties.items():
        if not isinstance(value, dict):
            value = {}
        specs.append(
            {
                "name": str(key),
                "type": schema_to_value_type(value),
                "required": key in required,
                "default": value.get("default"),
                "description": value.get("description"),
                "label": input_labels.get(str(key)) or str(value.get("title") or key),
            }
        )
    return specs


async def _tenant_artifact_operator_specs(*, db: AsyncSession, tenant_id: UUID) -> list[dict[str, Any]]:
    from app.db.postgres.models.artifact_runtime import ArtifactKind
    from app.services.artifact_runtime.registry_service import ArtifactRegistryService

    artifacts = await ArtifactRegistryService(db).list_accessible_artifacts(
        tenant_id=tenant_id,
        kind=ArtifactKind.AGENT_NODE,
    )
    specs: list[dict[str, Any]] = []
    for artifact in artifacts:
        revision = artifact.latest_draft_revision or artifact.latest_published_revision
        if revision is None:
            continue
        agent_contract = dict(revision.agent_contract or {}) if revision.agent_contract is not None else {}
        node_ui = dict(agent_contract.get("node_ui") or {}) if isinstance(agent_contract.get("node_ui"), dict) else {}
        input_schema = dict(agent_contract.get("input_schema") or {}) if isinstance(agent_contract.get("input_schema"), dict) else {}
        output_schema = dict(agent_contract.get("output_schema") or {}) if isinstance(agent_contract.get("output_schema"), dict) else {}
        config_schema = dict(revision.config_schema or {}) if revision.config_schema is not None else {}
        outputs = contract_fields_from_schema(output_schema, fallback_key="result")
        specs.append(
            {
                "type": str(artifact.id),
                "category": "action",
                "display_name": str(revision.display_name or artifact.display_name),
                "description": str(revision.description or artifact.description or "Artifact-backed node"),
                "reads": list(agent_contract.get("state_reads") or []),
                "writes": list(agent_contract.get("state_writes") or []),
                "config_schema": config_schema,
                "field_contracts": {},
                "output_contract": {"fields": outputs},
                "ui": {
                    "icon": str(node_ui.get("icon") or "Package"),
                    "color": str(node_ui.get("color") or "#64748b"),
                    "inputType": str(node_ui.get("inputType") or "any"),
                    "outputType": str(node_ui.get("outputType") or "context"),
                    "configFields": _artifact_config_fields_from_schema(config_schema),
                    "inputs": _artifact_input_specs(input_schema, node_ui),
                    "outputs": outputs,
                    "isArtifact": True,
                    "artifactId": str(artifact.id),
                    "artifactRevisionId": str(revision.id),
                },
            }
        )
    return specs

@router.get("/operators")
async def list_operators(
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """
    List all available agent operators including artifacts.
    """
    from app.agent.registry import AgentOperatorRegistry
    
    # Ensure artifacts are registered (lazy load if needed)
    from app.agent.executors.standard import register_standard_operators
    register_standard_operators()
    
    operators = AgentOperatorRegistry.list_operators()
    payload = [op.model_dump() for op in operators]
    payload.extend(await _tenant_artifact_operator_specs(db=db, tenant_id=context["tenant_id"]))
    return payload


@router.get("/nodes/catalog")
async def list_node_catalog(
    _: Dict[str, Any] = Depends(require_scopes("agents.read")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    del context, db
    from app.agent.registry import AgentOperatorRegistry
    from app.agent.executors.standard import register_standard_operators

    register_standard_operators()
    operators = AgentOperatorRegistry.list_operators()
    catalog = []
    for spec in operators:
        config_schema = spec.config_schema if isinstance(spec.config_schema, dict) else {}
        required_fields = config_schema.get("required") if isinstance(config_schema.get("required"), list) else []
        catalog.append(
            {
                "type": spec.type,
                "name": spec.display_name,
                "description": spec.description,
                "reads": list(spec.reads or []),
                "writes": list(spec.writes or []),
                "config_schema": config_schema,
                "ui_schema": spec.ui if isinstance(spec.ui, dict) else {},
                "required_fields": [str(item) for item in required_fields],
            }
        )
    return {"nodes": catalog}


@router.post("/nodes/schema")
async def get_node_schemas(
    request: NodeSchemaRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.read")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    del context, db
    node_types = [str(item).strip() for item in (request.node_types or []) if str(item).strip()]
    if not node_types:
        raise HTTPException(status_code=422, detail="node_types must be a non-empty array")

    from app.agent.registry import AgentOperatorRegistry
    from app.agent.executors.standard import register_standard_operators

    register_standard_operators()
    schemas: Dict[str, Dict[str, Any]] = {}
    unknown: list[str] = []

    for node_type in node_types:
        spec = AgentOperatorRegistry.get(node_type)
        if spec is None:
            unknown.append(node_type)
            continue
        config_schema = spec.config_schema if isinstance(spec.config_schema, dict) else {}
        required_fields = config_schema.get("required") if isinstance(config_schema.get("required"), list) else []
        schemas[node_type] = {
            "config_schema": config_schema,
            "ui_schema": spec.ui if isinstance(spec.ui, dict) else {},
            "required_fields": [str(item) for item in required_fields],
            "reads": list(spec.reads or []),
            "writes": list(spec.writes or []),
            "graph_node_contract": {
                "required_fields": ["id", "type", "position"],
                "field_shapes": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "const": spec.type},
                    "position": {
                        "type": "object",
                        "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                        "required": ["x", "y"],
                        "additionalProperties": False,
                    },
                    "label": {"type": "string"},
                    "config": config_schema,
                    "data": {"type": "object"},
                    "input_mappings": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "example_node": {
                    "id": f"{spec.type}_1",
                    "type": spec.type,
                    "position": {"x": 0, "y": 0},
                    "config": {},
                },
            },
        }

    return {
        "schemas": schemas,
        "unknown": unknown,
        "graph_create_contract": {
            "required_fields": ["nodes", "edges"],
            "node_required_fields": ["id", "type", "position"],
            "edge_required_fields": ["id", "source", "target"],
            "edge_field_shapes": {
                "id": {"type": "string"},
                "source": {"type": "string"},
                "target": {"type": "string"},
                "type": {"type": "string", "enum": ["control", "data"]},
                "source_handle": {"type": "string"},
                "target_handle": {"type": "string"},
                "label": {"type": "string"},
                "condition": {"type": "string"},
            },
        },
    }


# =============================================================================
# CRUD Endpoints
# =============================================================================

@router.get("", response_model=AgentListResponse)
async def list_agents(
    status: str = None,
    skip: int = 0,
    limit: int = 50,
    compact: bool = Query(False),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """List all agents."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    agents, total = await service.list_agents(status=status, skip=skip, limit=limit, compact=compact)
    
    return AgentListResponse(
        agents=[agent_to_response(a, compact=compact) for a in agents],
        total=total
    )


@router.post("", response_model=AgentResponse)
async def create_agent(
    request: CreateAgentRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.create_agent(
            data=CreateAgentData(
                name=request.name,
                slug=request.slug,
                description=request.description,
                graph_definition=request.graph_definition.model_dump() if request.graph_definition else {},
                memory_config=request.memory_config,
                execution_constraints=request.execution_constraints,
                workload_scope_profile=request.workload_scope_profile,
                workload_scope_overrides=request.workload_scope_overrides,
            ),
            user_id=context["user"].id if context.get("user") else None
        )
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Get an agent by ID."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.get_agent(agent_id)
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.put("/{agent_id}", response_model=AgentResponse)
@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    request: UpdateAgentRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Update an agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.update_agent(agent_id, UpdateAgentData(
            name=request.name,
            description=request.description,
            graph_definition=request.graph_definition.model_dump() if request.graph_definition else None,
            memory_config=request.memory_config,
            execution_constraints=request.execution_constraints,
            workload_scope_profile=request.workload_scope_profile,
            workload_scope_overrides=request.workload_scope_overrides,
        ), user_id=context["user"].id if context.get("user") else None)
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)
@router.put("/{agent_id}/graph", response_model=AgentResponse)
async def update_graph(
    agent_id: UUID,
    request: GraphDefinitionSchema,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Update agent graph."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        agent = await service.update_graph(agent_id, request.model_dump())
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Delete or archive an agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)

    await ensure_sensitive_action_approved(
        principal=principal,
        tenant_id=tenant_id,
        subject_type="agent",
        subject_id=str(agent_id),
        action_scope="agents.delete",
        db=db,
    )

    try:
        return await service.delete_agent(agent_id)
    except AgentServiceError as e:
        handle_service_error(e)


# =============================================================================
# Validation & Publishing
# =============================================================================

@router.post("/{agent_id}/validate")
async def validate_agent(
    agent_id: UUID,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Validate agent graph."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        result = await service.validate_agent(agent_id)
        return {"valid": result.valid, "errors": result.errors, "warnings": result.warnings}
    except AgentServiceError as e:
        handle_service_error(e)


@router.post("/{agent_id}/publish", response_model=AgentResponse)
async def publish_agent(
    agent_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Publish an agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)

    await ensure_sensitive_action_approved(
        principal=principal,
        tenant_id=tenant_id,
        subject_type="agent",
        subject_id=str(agent_id),
        action_scope="agents.publish",
        db=db,
    )

    try:
        agent = await service.publish_agent(agent_id, user_id=context["user"].id if context.get("user") else None)
        return agent_to_response(agent)
    except AgentServiceError as e:
        handle_service_error(e)


# =============================================================================
# Versioning
# =============================================================================

@router.get("/{agent_id}/versions")
async def list_versions(
    agent_id: UUID, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """List agent versions."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        versions = await service.list_versions(agent_id)
        return {"versions": versions}
    except AgentServiceError as e:
        handle_service_error(e)


@router.get("/{agent_id}/versions/{version}")
async def get_version(
    agent_id: UUID, 
    version: int, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Get specific version."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        return await service.get_version(agent_id, version)
    except AgentServiceError as e:
        handle_service_error(e)


# =============================================================================
# Execution
# =============================================================================

@router.post("/{agent_id}/execute", response_model=ExecuteAgentResponse)
async def execute_agent(
    agent_id: UUID,
    request: ExecuteAgentRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Execute a published agent."""
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    
    try:
        request_context = dict(request.context or {}) if isinstance(request.context, dict) else {}
        request_context.setdefault("tenant_id", str(tenant_id) if tenant_id is not None else None)
        request_context.setdefault("user_id", str(context["user"].id) if context.get("user") else context.get("initiator_user_id"))
        request_context.setdefault("requested_scopes", context.get("scopes", []))
        if context.get("grant_id"):
            request_context.setdefault("grant_id", context.get("grant_id"))
        if context.get("principal_id"):
            request_context.setdefault("principal_id", context.get("principal_id"))
        if context.get("initiator_user_id"):
            request_context.setdefault("initiator_user_id", context.get("initiator_user_id"))

        result = await service.execute_agent(agent_id, ExecuteAgentData(
            input=request.input,
            messages=request.messages,
            context=request_context,
        ), user_id=context["user"].id if context.get("user") else None)
        # Convert LangChain messages to dicts for Pydantic validation
        serialized_messages = []
        for msg in result.messages:
            if isinstance(msg, dict):
                serialized_messages.append(msg)
            elif hasattr(msg, "model_dump"):
                serialized_messages.append(msg.model_dump())
            elif hasattr(msg, "dict"):
                serialized_messages.append(msg.dict())
            else:
                serialized_messages.append({"content": str(msg), "type": "unknown"})

        return ExecuteAgentResponse(
            run_id=result.run_id,
            output=result.output,
            steps=result.steps,
            messages=serialized_messages,
            usage=result.usage,
        )
    except QuotaExceededError as exc:
        return JSONResponse(status_code=429, content=exc.to_payload())
    except AgentServiceError as e:
        handle_service_error(e)


@router.post("/{agent_id}/stream")
async def stream_agent(
    agent_id: UUID,
    request: ExecuteAgentRequest,
    mode: Optional[str] = None, # "debug" or "production"
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Stream agent execution (SSE).
    Supports 'debug' (Playground) and 'production' (End-User) modes.
    """
    from app.agent.execution.service import AgentExecutorService
    from app.agent.execution.types import ExecutionMode
    from app.agent.execution.adapter import StreamAdapter
    
    # 1. Determine Mode
    # Default to PRODUCTION for safety
    execution_mode = ExecutionMode.PRODUCTION
    
    # Allow override if internal user (authenticated via standard auth)
    # TODO: Check specifically for "service account" or "public key" vs "user session"
    # For now, get_agent_context implies internal user/admin. 
    # Real public users would use a different specific auth dependency (e.g. get_public_agent_context).
    # Assuming get_agent_context ensures an internal user/member:
    if mode and mode.lower() == "debug":
        execution_mode = ExecutionMode.DEBUG

    executor = AgentExecutorService(db=db)
    
    # 2. Identify or Create Run
    run_id = request.run_id
    resume_payload = None
    
    if run_id:
        # Resume existing run
        try:
            # For playground, user message is the resume payload
            if request.context:
                resume_payload = request.context
            elif request.input:
                resume_payload = {"input": request.input}
            else:
                resume_payload = {}
            await executor.resume_run(run_id, resume_payload, background=False)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cannot resume run {run_id}: {e}")
    else:
        # Start new run
        current_messages = [msg.model_dump() if hasattr(msg, "model_dump") else msg for msg in request.messages]

        tenant_id = context.get("tenant_id")
        request_context = dict(request.context or {}) if isinstance(request.context, dict) else {}
        request_context.setdefault("token", context.get("auth_token"))
        request_context.setdefault("tenant_id", str(tenant_id) if tenant_id is not None else None)
        request_context.setdefault("user_id", str(context["user"].id) if context.get("user") else context.get("initiator_user_id"))
        # Do not inject caller scope inventory by default.
        # Delegation grants should request either explicit caller-provided scopes
        # or workload-context scopes in delegated chains.
        explicit_requested_scopes = None
        if isinstance(request.context, dict):
            maybe_explicit_scopes = request.context.get("requested_scopes")
            if isinstance(maybe_explicit_scopes, list):
                explicit_requested_scopes = maybe_explicit_scopes
        if explicit_requested_scopes is not None:
            request_context["requested_scopes"] = explicit_requested_scopes
        elif context.get("grant_id"):
            request_context["requested_scopes"] = context.get("scopes", [])
        request_context.setdefault("grant_id", context.get("grant_id"))
        request_context.setdefault("principal_id", context.get("principal_id"))
        request_context.setdefault("initiator_user_id", context.get("initiator_user_id"))
        input_params = {
            "messages": current_messages,
            "input": request.input,
            "attachment_ids": [str(item) for item in request.attachment_ids],
            "thread_id": str(request.thread_id) if request.thread_id else None,
            "context": request_context,
        }
        # Start run with explicit mode metadata
        requested_scopes = request_context.get("requested_scopes") if isinstance(request_context.get("requested_scopes"), list) else None
        initiating_user_id = context["user"].id if context.get("user") else None
        try:
            run_id = await executor.start_run(
                agent_id,
                input_params,
                user_id=initiating_user_id,
                background=False,
                mode=execution_mode,
                requested_scopes=requested_scopes,
                thread_id=request.thread_id,
            )
        except QuotaExceededError as exc:
            return JSONResponse(status_code=429, content=exc.to_payload())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    run_row = await db.get(AgentRun, run_id)
    thread_id_value = str(run_row.thread_id) if run_row and run_row.thread_id else None

    async def event_generator():
        # raw stream from engine (full firehose)
        raw_stream = executor.run_and_stream(run_id, db, resume_payload, mode=execution_mode)
        
        # filtered stream via adapter
        filtered_stream = StreamAdapter.filter_stream(raw_stream, execution_mode)

        # Initial Event + padding to force proxy flush.
        seq = 1
        yield ": " + (" " * 4096) + "\n\n"
        if _stream_v2_enforced():
            accepted = build_stream_v2_event(
                seq=seq,
                run_id=str(run_id),
                event="run.accepted",
                stage="run",
                payload={"status": "running", "thread_id": thread_id_value},
            )
            seq += 1
            yield f"data: {json.dumps(accepted, default=str)}\n\n"
        else:
            yield f"data: {json.dumps({'event': 'run_id', 'run_id': str(run_id)})}\n\n"

        try:
            async for event_dict in filtered_stream:
                if _stream_v2_enforced():
                    mapped_event, stage, payload, diagnostics = normalize_filtered_event_to_v2(raw_event=event_dict)
                    envelope = build_stream_v2_event(
                        seq=seq,
                        run_id=str(run_id),
                        event=mapped_event,
                        stage=stage,
                        payload=payload,
                        diagnostics=diagnostics,
                    )
                    seq += 1
                    yield f"data: {json.dumps(envelope, default=str)}\n\n"
                else:
                    yield f"data: {json.dumps(event_dict, default=str)}\n\n"
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"[STREAM] Error during stream: {e}")
            if _stream_v2_enforced():
                envelope = build_stream_v2_event(
                    seq=seq,
                    run_id=str(run_id),
                    event="run.failed",
                    stage="run",
                    payload={"error": str(e)},
                    diagnostics=[{"message": str(e)}],
                )
                yield f"data: {json.dumps(envelope, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Content-Encoding": "identity", # Disable compression
            "X-Thread-ID": thread_id_value or "",
        }
    )
    
@router.post("/{agent_id}/run", response_model=Dict[str, Any])
async def start_run_v2(
    agent_id: UUID,
    request: ExecuteAgentRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Start an agent execution using the new AgentExecutorService (Phase 4 engine).
    Returns the Run ID immediately.
    """
    from app.agent.execution.service import AgentExecutorService
    
    tenant_id = context["tenant_id"]
    # Ensure user has access
    service = AgentService(db=db, tenant_id=tenant_id)
    try:
        await service.get_agent(agent_id) # Validates existence and checks ownership implicitly
    except Exception:
        raise
    
    executor = AgentExecutorService(db=db)
    
    # Construct input params
    # Convert Pydantic messages to dicts
    current_messages = [msg.model_dump() if hasattr(msg, "model_dump") else msg for msg in request.messages]

    tenant_id = context.get("tenant_id")
    request_context = dict(request.context or {}) if isinstance(request.context, dict) else {}
    request_context.setdefault("token", context.get("auth_token"))
    request_context.setdefault("tenant_id", str(tenant_id) if tenant_id is not None else None)
    request_context.setdefault("user_id", str(context["user"].id) if context.get("user") else context.get("initiator_user_id"))
    explicit_requested_scopes = None
    if isinstance(request.context, dict):
        maybe_explicit_scopes = request.context.get("requested_scopes")
        if isinstance(maybe_explicit_scopes, list):
            explicit_requested_scopes = maybe_explicit_scopes
    if explicit_requested_scopes is not None:
        request_context["requested_scopes"] = explicit_requested_scopes
    elif context.get("grant_id"):
        request_context["requested_scopes"] = context.get("scopes", [])
    request_context.setdefault("grant_id", context.get("grant_id"))
    request_context.setdefault("principal_id", context.get("principal_id"))
    request_context.setdefault("initiator_user_id", context.get("initiator_user_id"))
    input_params = {
        "messages": current_messages,
        "input": request.input,
        "attachment_ids": [str(item) for item in request.attachment_ids],
        "thread_id": str(request.thread_id) if request.thread_id else None,
        "context": request_context,
    }
    
    try:
        requested_scopes = request_context.get("requested_scopes") if isinstance(request_context.get("requested_scopes"), list) else None
        initiating_user_id = context["user"].id if context.get("user") else None
        run_id = await executor.start_run(
            agent_id,
            input_params,
            user_id=initiating_user_id,
            requested_scopes=requested_scopes,
            thread_id=request.thread_id,
        )
        run_row = await db.get(AgentRun, run_id)
        return {
            "run_id": str(run_id),
            "thread_id": str(run_row.thread_id) if run_row and run_row.thread_id else None,
        }
    except QuotaExceededError as exc:
        return JSONResponse(status_code=429, content=exc.to_payload())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/attachments/upload")
async def upload_agent_attachments(
    agent_id: UUID,
    files: list[UploadFile] = File(...),
    thread_id: Optional[UUID] = Form(default=None),
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = context["tenant_id"]
    service = AgentService(db=db, tenant_id=tenant_id)
    agent = await service.get_agent(agent_id)

    owner = RuntimeAttachmentOwner(
        tenant_id=agent.tenant_id,
        surface=AgentThreadSurface.internal,
        user_id=(
            context["user"].id
            if context.get("user") is not None
            else _optional_uuid(context.get("initiator_user_id"))
        ),
        agent_id=agent.id,
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


@router.post("/runs/{run_id}/resume", response_model=Dict[str, Any])
async def resume_run_v2(
    run_id: UUID,
    request: Dict[str, Any], # Payload depends on what the node waits for
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Resume a paused agent run.
    """
    from app.agent.execution.service import AgentExecutorService
    from app.db.postgres.models.agents import AgentRun
    
    executor = AgentExecutorService(db=db)

    run_result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = run_result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if str(run.tenant_id) != str(context.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    # User principals can only resume their own runs (unless system admin).
    if not context.get("is_service"):
        user = context.get("user")
        if user is not None and not is_platform_admin_role(getattr(user, "role", None)):
            allowed_user_ids = {
                str(uid)
                for uid in (run.user_id, run.initiator_user_id)
                if uid is not None
            }
            if allowed_user_ids and str(user.id) not in allowed_user_ids:
                raise HTTPException(status_code=403, detail="Run ownership mismatch")
    else:
        # Workload principals must match if the run is tied to a principal.
        principal_id = context.get("principal_id")
        if run.workload_principal_id is not None and principal_id is not None:
            if str(run.workload_principal_id) != str(principal_id):
                raise HTTPException(status_code=403, detail="Run principal mismatch")
    
    await executor.resume_run(run_id, request)
    return {"status": "resumed"}


@router.post("/runs/{run_id}/cancel", response_model=Dict[str, Any])
async def cancel_run_v2(
    run_id: UUID,
    request: CancelRunRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    run_result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = run_result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if str(run.tenant_id) != str(context.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    if not context.get("is_service"):
        user = context.get("user")
        if user is not None and not is_platform_admin_role(getattr(user, "role", None)):
            allowed_user_ids = {
                str(uid)
                for uid in (run.user_id, run.initiator_user_id)
                if uid is not None
            }
            if allowed_user_ids and str(user.id) not in allowed_user_ids:
                raise HTTPException(status_code=403, detail="Run ownership mismatch")

    status = str(getattr(run.status, "value", run.status))
    if status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value}:
        return {
            "run_id": str(run.id),
            "status": status,
            "thread_id": str(run.thread_id) if run.thread_id else None,
        }

    partial_text = str(request.assistant_output_text or "").strip()
    run.status = RunStatus.cancelled
    run.completed_at = datetime.utcnow()
    run.error_message = None

    output_result = dict(run.output_result or {}) if isinstance(run.output_result, dict) else {}
    messages = output_result.get("messages")
    if not isinstance(messages, list):
        messages = []
    if partial_text:
        messages.append({"role": "assistant", "content": partial_text})
        output_result["final_output"] = partial_text
    output_result["messages"] = messages
    run.output_result = output_result

    if run.thread_id:
        thread_service = ThreadService(db)
        input_text = None
        attachment_ids: list[UUID] = []
        if isinstance(run.input_params, dict):
            raw_input = run.input_params.get("input_display_text") or run.input_params.get("input")
            if isinstance(raw_input, str):
                input_text = raw_input
            raw_attachment_ids = run.input_params.get("attachment_ids")
            if isinstance(raw_attachment_ids, list):
                for item in raw_attachment_ids:
                    try:
                        attachment_ids.append(UUID(str(item)))
                    except Exception:
                        continue
        await thread_service.start_turn(
            thread_id=run.thread_id,
            run_id=run.id,
            user_input_text=input_text,
            attachment_ids=attachment_ids,
            metadata={"cancelled": True},
        )
        await thread_service.complete_turn(
            run_id=run.id,
            status=AgentThreadTurnStatus.cancelled,
            assistant_output_text=partial_text or None,
            usage_tokens=int(run.usage_tokens or 0),
            metadata={"cancelled": True},
        )

    await db.commit()
    return {
        "run_id": str(run.id),
        "status": RunStatus.cancelled.value,
        "thread_id": str(run.thread_id) if run.thread_id else None,
    }


@router.get("/runs/{run_id}", response_model=Dict[str, Any])
async def get_run_status(
    run_id: UUID,
    include_tree: bool = Query(False, description="Include orchestration run tree for debug UIs"),
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status and result of a run.
    """
    from app.db.postgres.models.agents import AgentRun, AgentTrace
    
    result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = result.scalars().first()
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if str(run.tenant_id) != str(context.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    payload = {
        "id": str(run.id),
        "status": run.status.value if hasattr(run.status, "value") else run.status,
        "result": run.output_result,
        "error": run.error_message,
        "checkpoint": run.checkpoint,  # Debugging
        "lineage": {
            "root_run_id": str(run.root_run_id) if run.root_run_id else None,
            "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
            "parent_node_id": run.parent_node_id,
            "depth": int(run.depth or 0),
            "spawn_key": run.spawn_key,
            "orchestration_group_id": str(run.orchestration_group_id) if run.orchestration_group_id else None,
        },
    }
    if str(payload["status"]) == RunStatus.paused.value:
        from app.agent.execution.service import AgentExecutorService
        from app.services.prompt_reference_resolver import PromptReferenceResolver

        agent = await db.get(Agent, run.agent_id)
        checkpoint = run.checkpoint if isinstance(run.checkpoint, dict) else {}
        next_ids = checkpoint.get("next")
        if agent is not None and next_ids:
            graph_payload = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
            graph_payload = await PromptReferenceResolver(db, agent.tenant_id).resolve_graph_definition(graph_payload)
            nodes = graph_payload.get("nodes") if isinstance(graph_payload.get("nodes"), list) else []
            node_index = {str(node.get("id") or ""): node for node in nodes if isinstance(node, dict)}
            resolved_next = []
            for next_id in (next_ids if isinstance(next_ids, list) else [next_ids]):
                node = node_index.get(str(next_id))
                if node is None:
                    resolved_next.append({"id": str(next_id)})
                    continue
                resolved_next.append(
                    AgentExecutorService._build_paused_node_payload(
                        node=node,
                        state=checkpoint if isinstance(checkpoint, dict) else {},
                    )
                )
            payload["paused_nodes"] = resolved_next
    if include_tree:
        from app.services.orchestration_kernel_service import OrchestrationKernelService
        payload["run_tree"] = await OrchestrationKernelService(db).query_tree(run_id=run.id)
    return payload


@router.get("/runs/{run_id}/tree", response_model=Dict[str, Any])
async def get_run_tree(
    run_id: UUID,
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    from app.services.orchestration_kernel_service import OrchestrationKernelService
    from app.db.postgres.models.agents import AgentRun

    run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if str(run.tenant_id) != str(context.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    return await OrchestrationKernelService(db).query_tree(run_id=run_id)
