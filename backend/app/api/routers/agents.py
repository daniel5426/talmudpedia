"""
Agents API Router - Thin dispatch layer for agent endpoints.

Routers should only: Validate, Authenticate, Dispatch.
All business logic lives in AgentService.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
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
    AgentInputValidationError,
    AgentPublishedError,
    AgentNotPublishedError,
)
from app.services.resource_policy_quota_service import ResourcePolicyQuotaExceeded
from app.services.usage_quota_service import QuotaExceededError
from app.agent.graph.contracts import contract_fields_from_schema, schema_to_value_type
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
from app.db.postgres.models.registry import ToolRegistry
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timezone
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.db.postgres.models.agents import RunStatus
from app.agent.execution.persisted_stream import stream_persisted_run_events
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.context_window_service import ContextWindowService
from app.services.model_accounting import usage_payload_from_run
from app.services.orchestration_kernel_service import OrchestrationKernelService
from app.services.organization_bootstrap_service import OrganizationBootstrapService
from app.services.control_plane.agents_admin_service import (
    AgentAdminService,
    CreateAgentInput as ControlPlaneCreateAgentInput,
    StartAgentRunInput as ControlPlaneStartAgentRunInput,
    UpdateAgentInput as ControlPlaneUpdateAgentInput,
)
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.contracts import ListQuery
from app.services.control_plane.errors import ControlPlaneError
from app.services.runtime_surface import (
    RuntimeChatRequest,
    RuntimeEventView,
    RuntimeRunControlContext,
    RuntimeStreamOptions,
    RuntimeSurfaceContext,
    RuntimeSurfaceService,
)
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


def _serialize_run_usage(run: AgentRun) -> dict[str, Any]:
    return usage_payload_from_run(run) or {}


def _control_plane_ctx_from_agent_context(context: Dict[str, Any]) -> ControlPlaneContext:
    return ControlPlaneContext(
        organization_id=UUID(str(context["organization_id"])),
        project_id=_optional_uuid(context.get("project_id")),
        user=context.get("user"),
        user_id=getattr(context.get("user"), "id", None),
        auth_token=context.get("auth_token"),
        scopes=tuple(context.get("scopes") or ()),
        is_service=bool(context.get("is_service", False)),
    )


# =============================================================================
# Helpers
# =============================================================================

async def get_agent_context(
    request: Request,
    context: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns a context dict with 'user' and 'organization_id'.
    Users can manage agents if they are System Admins OR have an Org role.
    """
    token = context.get("auth_token")
    current_user = context.get("user")
    if current_user is None:
        raise HTTPException(status_code=403, detail="Not authorized to manage agents")

    # Prefer explicit organization header so multi-organization users can target the selected organization.
    header_organization = request.headers.get("X-Organization-ID")
    resolved_organization: UUID | None = None
    if header_organization:
        try:
            header_organization_uuid = UUID(str(header_organization))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid X-Organization-ID header")
        resolved_organization = header_organization_uuid
    else:
        organization_id = context.get("organization_id")
        if organization_id is None:
            raise HTTPException(status_code=403, detail="Organization context required")
        try:
            resolved_organization = UUID(str(organization_id))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid organization context")

    membership_res = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == current_user.id,
            OrgMembership.organization_id == resolved_organization,
        ).limit(1)
    )
    membership = membership_res.scalar_one_or_none()
    if membership is None and not is_platform_admin_role(getattr(current_user, "role", None)):
        raise HTTPException(status_code=403, detail="Not a member of the requested organization")

    return {
        "user": current_user,
        "organization_id": resolved_organization,
        "project_id": _optional_uuid(context.get("project_id")),
        "auth_token": token,
        "is_service": False,
        "scopes": context.get("scopes", []),
    }


def agent_to_response(agent, compact: bool = False, *, tool_binding: ToolRegistry | None = None) -> AgentResponse:
    """Convert Agent model to response."""
    return AgentResponse(
        id=agent.id,
        organization_id=agent.organization_id,
        project_id=getattr(agent, "project_id", None),
        name=agent.name,
        system_key=getattr(agent, "system_key", None),
        description=agent.description,
        graph_definition={"nodes": [], "edges": []} if compact else (agent.graph_definition or {"nodes": [], "edges": []}),
        memory_config={} if compact else (agent.memory_config or {}),
        execution_constraints={} if compact else (agent.execution_constraints or {}),
        version=agent.version,
        status=agent.status.value if hasattr(agent.status, "value") else (agent.status or "draft"),

        is_active=agent.is_active,
        is_public=agent.is_public,
        show_in_playground=bool(getattr(agent, "show_in_playground", True)),
        default_embed_policy_set_id=getattr(agent, "default_embed_policy_set_id", None),
        tool_binding_status=(
            str(getattr(getattr(tool_binding, "status", None), "value", getattr(tool_binding, "status", ""))).lower() or None
        ) if tool_binding is not None else None,
        is_tool_enabled=tool_binding is not None and bool(getattr(tool_binding, "is_active", False)),
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
                "message": "Graph write rejected",
                "errors": e.errors,
            },
        )
    if isinstance(e, AgentInputValidationError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": e.message,
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


async def _organization_artifact_operator_specs(*, db: AsyncSession, organization_id: UUID) -> list[dict[str, Any]]:
    from app.db.postgres.models.artifact_runtime import ArtifactKind
    from app.services.artifact_runtime.registry_service import ArtifactRegistryService

    artifacts = await ArtifactRegistryService(db).list_accessible_artifacts(
        organization_id=organization_id,
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
    payload.extend(await _organization_artifact_operator_specs(db=db, organization_id=context["organization_id"]))
    return payload


@router.get("/nodes/catalog")
async def list_node_catalog(
    _: Dict[str, Any] = Depends(require_scopes("agents.read")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    del context
    try:
        return await AgentAdminService(db).list_node_catalog()
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("/nodes/schema")
async def get_node_schemas(
    request: NodeSchemaRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.read")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    del context
    try:
        result = await AgentAdminService(db).get_node_schemas(node_types=list(request.node_types or []))
        return {
            "schemas": result["schemas"],
            "unknown": [],
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
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


# =============================================================================
# CRUD Endpoints
# =============================================================================

@router.get("", response_model=dict[str, Any])
async def list_agents(
    status: str = None,
    skip: int = 0,
    limit: int = 20,
    view: str = "summary",
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """List all agents."""
    organization_id= context["organization_id"]
    project_id = context.get("project_id")
    bootstrap = OrganizationBootstrapService(db)
    did_backfill = False
    if project_id is not None:
        did_backfill = await bootstrap.ensure_project_default_agents_if_missing(
            organization_id=organization_id,
            project_id=project_id,
            actor_user_id=getattr(context.get("user"), "id", None),
        )
    if did_backfill or db.new or db.dirty:
        await db.commit()
    try:
        query = ListQuery.from_payload({"skip": skip, "limit": limit, "view": view})
        page = await AgentAdminService(db).list_agents(
            ctx=_control_plane_ctx_from_agent_context(context),
            query=query,
            status=status,
        )
        return page.to_payload()
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("", response_model=AgentResponse)
async def create_agent(
    request: CreateAgentRequest,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent."""
    try:
        payload = await AgentAdminService(db).create_agent(
            ctx=_control_plane_ctx_from_agent_context(context),
            params=ControlPlaneCreateAgentInput(
                name=request.name,
                description=request.description,
                graph_definition=request.graph_definition.model_dump() if request.graph_definition else {},
                memory_config=request.memory_config,
                execution_constraints=request.execution_constraints,
            ),
        )
        return AgentResponse(**payload)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID, 
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Get an agent by ID."""
    try:
        payload = await AgentAdminService(db).get_agent(ctx=_control_plane_ctx_from_agent_context(context), agent_id=agent_id)
        return AgentResponse(**payload)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


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
    try:
        payload = await AgentAdminService(db).update_agent(
            ctx=_control_plane_ctx_from_agent_context(context),
            agent_id=agent_id,
            params=ControlPlaneUpdateAgentInput(
                name=request.name,
                description=request.description,
                graph_definition=request.graph_definition.model_dump() if request.graph_definition else None,
                memory_config=request.memory_config,
                execution_constraints=request.execution_constraints,
            ),
        )
        return AgentResponse(**payload)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
@router.put("/{agent_id}/graph", response_model=AgentResponse)
async def update_graph(
    agent_id: UUID,
    request: GraphDefinitionSchema,
    _: Dict[str, Any] = Depends(require_scopes("agents.write")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    """Update agent graph."""
    organization_id= context["organization_id"]
    service = AgentService(db=db, organization_id=organization_id, project_id=context.get("project_id"))
    
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
    organization_id= context["organization_id"]
    service = AgentService(db=db, organization_id=organization_id, project_id=context.get("project_id"))

    await ensure_sensitive_action_approved(
        principal=principal,
        organization_id=organization_id,
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
    try:
        return await AgentAdminService(db).validate_agent(ctx=_control_plane_ctx_from_agent_context(context), agent_id=agent_id)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("/{agent_id}/publish", response_model=AgentResponse)
async def publish_agent(
    agent_id: UUID,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("agents.publish")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db)
):
    """Publish an agent."""
    organization_id= context["organization_id"]

    await ensure_sensitive_action_approved(
        principal=principal,
        organization_id=organization_id,
        subject_type="agent",
        subject_id=str(agent_id),
        action_scope="agents.publish",
        db=db,
    )

    try:
        payload = await AgentAdminService(db).publish_agent(ctx=_control_plane_ctx_from_agent_context(context), agent_id=agent_id)
        return AgentResponse(**payload)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


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
    organization_id= context["organization_id"]
    service = AgentService(db=db, organization_id=organization_id, project_id=context.get("project_id"))
    
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
    organization_id= context["organization_id"]
    service = AgentService(db=db, organization_id=organization_id, project_id=context.get("project_id"))
    
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
    organization_id= context["organization_id"]
    service = AgentService(db=db, organization_id=organization_id, project_id=context.get("project_id"))
    
    try:
        request_context = dict(request.context or {}) if isinstance(request.context, dict) else {}
        request_context.setdefault("organization_id", str(organization_id) if organization_id is not None else None)
        request_context.setdefault("user_id", str(context["user"].id) if context.get("user") else context.get("initiator_user_id"))
        if context.get("initiator_user_id"):
            request_context.setdefault("initiator_user_id", context.get("initiator_user_id"))

        result = await service.execute_agent(agent_id, ExecuteAgentData(
            input=request.input,
            messages=request.messages,
            state=request.state,
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
    except (QuotaExceededError, ResourcePolicyQuotaExceeded) as exc:
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

    organization_id= context.get("organization_id")
    request_context = dict(request.context or {}) if isinstance(request.context, dict) else {}
    request_context.setdefault("token", context.get("auth_token"))
    request_context.setdefault("organization_id", str(organization_id) if organization_id is not None else None)
    request_context.setdefault("project_id", str(context.get("project_id")) if context.get("project_id") else None)
    request_context.setdefault("user_id", str(context["user"].id) if context.get("user") else context.get("initiator_user_id"))
    request_context.setdefault("initiator_user_id", context.get("initiator_user_id"))

    try:
        return await RuntimeSurfaceService(db=db, executor_cls=AgentExecutorService).stream_chat(
            agent_id=agent_id,
            surface_context=RuntimeSurfaceContext(
                organization_id=organization_id,
                project_id=context.get("project_id"),
                surface=AgentThreadSurface.internal,
                event_view=RuntimeEventView.internal_full,
                user_id=context["user"].id if context.get("user") else None,
                context_defaults=request_context,
            ),
            request=RuntimeChatRequest(
                input=request.input,
                messages=[msg.model_dump() if hasattr(msg, "model_dump") else msg for msg in request.messages],
                attachment_ids=[str(item) for item in request.attachment_ids],
                state=dict(request.state or {}) if isinstance(request.state, dict) else {},
                context=dict(request.context or {}) if isinstance(request.context, dict) else {},
                client=dict(request.client or {}) if isinstance(request.client, dict) else {},
                thread_id=request.thread_id,
                run_id=request.run_id,
            ),
            options=RuntimeStreamOptions(
                execution_mode=execution_mode,
                preload_thread_messages=False,
                stream_v2_enforced=_stream_v2_enforced(),
                include_content_encoding_identity=True,
                include_run_id_header=True,
            ),
        )
    except (QuotaExceededError, ResourcePolicyQuotaExceeded) as exc:
        return JSONResponse(status_code=429, content=exc.to_payload())
    
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
    try:
        operation = await AgentAdminService(db).start_run(
            ctx=_control_plane_ctx_from_agent_context(context),
            agent_id=agent_id,
            params=ControlPlaneStartAgentRunInput(
                input=request.input,
                messages=[msg.model_dump() if hasattr(msg, "model_dump") else msg for msg in request.messages],
                context=request.context if isinstance(request.context, dict) else {},
                thread_id=request.thread_id,
            ),
        )
        return {
            "run_id": operation["operation"]["id"],
            "thread_id": operation.get("metadata", {}).get("thread_id"),
        }
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("/{agent_id}/attachments/upload")
async def upload_agent_attachments(
    agent_id: UUID,
    files: list[UploadFile] = File(...),
    thread_id: Optional[UUID] = Form(default=None),
    _: Dict[str, Any] = Depends(require_scopes("agents.execute")),
    context: Dict[str, Any] = Depends(get_agent_context),
    db: AsyncSession = Depends(get_db),
):
    organization_id= context["organization_id"]
    service = AgentService(db=db, organization_id=organization_id)
    agent = await service.get_agent(agent_id)

    owner = RuntimeAttachmentOwner(
        organization_id=agent.organization_id,
        surface=AgentThreadSurface.internal,
        user_id=(
            context["user"].id
            if context.get("user") is not None
            else _optional_uuid(context.get("initiator_user_id"))
        ),
        agent_id=agent.id,
        project_id=agent.project_id,
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

    if str(run.organization_id) != str(context.get("organization_id")):
        raise HTTPException(status_code=403, detail="Organization mismatch")
    if str(run.project_id) != str(context.get("project_id")):
        raise HTTPException(status_code=403, detail="Project mismatch")

    user = context.get("user")
    if user is not None and not is_platform_admin_role(getattr(user, "role", None)):
        allowed_user_ids = {
            str(uid)
            for uid in (run.user_id, run.initiator_user_id)
            if uid is not None
        }
        if allowed_user_ids and str(user.id) not in allowed_user_ids:
            raise HTTPException(status_code=403, detail="Run ownership mismatch")
    
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
    return await RuntimeSurfaceService(db).cancel_run(
        run_id=run_id,
        control=RuntimeRunControlContext(
            organization_id=context["organization_id"],
            project_id=context.get("project_id"),
            user_id=getattr(context.get("user"), "id", None),
            is_service=bool(context.get("is_service")),
            is_platform_admin=RuntimeSurfaceService.is_platform_admin(context.get("user")),
        ),
        assistant_output_text=request.assistant_output_text,
    )


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
    from app.db.postgres.models.agents import AgentTrace

    try:
        operation = await AgentAdminService(db).get_run(ctx=_control_plane_ctx_from_agent_context(context), run_id=run_id)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    payload = {
        "id": operation["operation"]["id"],
        "status": operation["operation"]["status"],
        "result": operation.get("result"),
        "error": (operation.get("error") or {}).get("message"),
        "checkpoint": operation.get("metadata", {}).get("checkpoint"),
        "run_usage": operation.get("metadata", {}).get("run_usage") or {},
        "context_window": operation.get("metadata", {}).get("context_window"),
        "lineage": operation.get("metadata", {}).get("lineage") or {},
    }
    run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id))
    if str(payload["status"]) == RunStatus.paused.value:
        from app.agent.execution.service import AgentExecutorService
        from app.services.prompt_reference_resolver import PromptReferenceResolver

        agent = await db.get(Agent, run.agent_id)
        checkpoint = run.checkpoint if isinstance(run.checkpoint, dict) else {}
        next_ids = checkpoint.get("next")
        if agent is not None and next_ids:
            graph_payload = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
            graph_payload = await PromptReferenceResolver(db, agent.organization_id).resolve_graph_definition(graph_payload)
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
    if str(run.organization_id) != str(context.get("organization_id")):
        raise HTTPException(status_code=403, detail="Organization mismatch")
    if str(run.project_id) != str(context.get("project_id")):
        raise HTTPException(status_code=403, detail="Project mismatch")
    return await OrchestrationKernelService(db).query_tree(run_id=run_id)
