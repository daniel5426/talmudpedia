from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.service import AgentExecutorService
from app.agent.registry import AgentOperatorRegistry
from app.agent.executors.standard import register_standard_operators
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.artifact_runtime import ArtifactKind
from app.db.postgres.models.registry import ToolRegistry
from app.graph_authoring import agent_catalog_item, agent_instance_contract, agent_node_spec, artifact_node_spec
from app.services.context_window_service import ContextWindowService
from app.services.file_spaces.service import FileSpaceService
from app.services.agent_service import (
    AgentGraphValidationError,
    AgentNotFoundError,
    AgentService,
    AgentServiceError,
    AgentSlugExistsError,
    AgentValidationResult,
    CreateAgentData,
    UpdateAgentData,
)
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.contracts import ListPage, ListQuery, OperationResult
from app.services.control_plane.errors import conflict, not_found, validation
from app.services.tool_binding_service import ToolBindingService
from app.services.model_accounting import usage_payload_from_run
from app.services.artifact_runtime.registry_service import ArtifactRegistryService


@dataclass(frozen=True)
class CreateAgentInput:
    name: str
    description: str | None = None
    graph_definition: dict[str, Any] | None = None
    memory_config: dict[str, Any] | None = None
    execution_constraints: dict[str, Any] | None = None
    show_in_playground: bool = True


@dataclass(frozen=True)
class UpdateAgentInput:
    name: str | None = None
    description: str | None = None
    graph_definition: dict[str, Any] | None = None
    memory_config: dict[str, Any] | None = None
    execution_constraints: dict[str, Any] | None = None
    show_in_playground: bool | None = None


@dataclass(frozen=True)
class StartAgentRunInput:
    input: str | None = None
    messages: list[dict[str, Any]] | None = None
    context: dict[str, Any] | None = None
    thread_id: UUID | None = None


class AgentAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _service(self, ctx: ControlPlaneContext) -> AgentService:
        return AgentService(db=self.db, organization_id=ctx.organization_id, project_id=ctx.project_id)

    async def list_agents(
        self,
        *,
        ctx: ControlPlaneContext,
        query: ListQuery,
        status: str | None = None,
    ) -> ListPage:
        service = self._service(ctx)
        agents, total = await service.list_agents(
            status=status,
            skip=query.skip,
            limit=query.limit,
            compact=query.view == "summary",
        )
        binding_service = ToolBindingService(self.db)
        items = []
        for agent in agents:
            tool_binding = await binding_service.get_agent_tool(agent.id)
            items.append(self.serialize_agent(agent, view=query.view, tool_binding=tool_binding))
        return ListPage(items=items, total=total, query=query)

    async def get_agent(self, *, ctx: ControlPlaneContext, agent_id: UUID) -> dict[str, Any]:
        try:
            agent = await self._service(ctx).get_agent(agent_id)
        except AgentNotFoundError as exc:
            raise not_found(str(exc)) from exc
        tool_binding = await ToolBindingService(self.db).get_agent_tool(agent.id)
        return self.serialize_agent(agent, tool_binding=tool_binding)

    async def create_agent(self, *, ctx: ControlPlaneContext, params: CreateAgentInput) -> dict[str, Any]:
        name = str(params.name or "").strip()
        if not name:
            raise validation("name is required", field="name")
        try:
            agent = await self._service(ctx).create_agent(
                CreateAgentData(
                    name=name,
                    description=params.description,
                    graph_definition=dict(params.graph_definition or {}),
                    memory_config=dict(params.memory_config or {}),
                    execution_constraints=dict(params.execution_constraints or {}),
                    show_in_playground=bool(params.show_in_playground),
                ),
                user_id=ctx.user_id,
            )
        except AgentSlugExistsError as exc:
            raise conflict(str(exc)) from exc
        except AgentGraphValidationError as exc:
            raise validation("Graph write rejected", errors=exc.errors) from exc
        except AgentServiceError as exc:
            raise validation(str(exc)) from exc
        tool_binding = await ToolBindingService(self.db).get_agent_tool(agent.id)
        return self.serialize_agent(agent, tool_binding=tool_binding)

    async def update_agent(self, *, ctx: ControlPlaneContext, agent_id: UUID, params: UpdateAgentInput) -> dict[str, Any]:
        if params.name is not None and not str(params.name).strip():
            raise validation("name cannot be blank", field="name")
        try:
            agent = await self._service(ctx).update_agent(
                agent_id,
                UpdateAgentData(
                    name=str(params.name).strip() if params.name is not None else None,
                    description=params.description,
                    graph_definition=params.graph_definition,
                    memory_config=params.memory_config,
                    execution_constraints=params.execution_constraints,
                    show_in_playground=params.show_in_playground,
                ),
                user_id=ctx.user_id,
            )
        except AgentNotFoundError as exc:
            raise not_found(str(exc)) from exc
        except AgentGraphValidationError as exc:
            raise validation("Graph write rejected", errors=exc.errors) from exc
        except AgentServiceError as exc:
            raise validation(str(exc)) from exc
        tool_binding = await ToolBindingService(self.db).get_agent_tool(agent.id)
        return self.serialize_agent(agent, tool_binding=tool_binding)

    async def validate_agent(self, *, ctx: ControlPlaneContext, agent_id: UUID) -> dict[str, Any]:
        try:
            result: AgentValidationResult = await self._service(ctx).validate_agent(agent_id)
        except AgentNotFoundError as exc:
            raise not_found(str(exc)) from exc
        except AgentServiceError as exc:
            raise validation(str(exc)) from exc
        return {"valid": result.valid, "errors": result.errors, "warnings": result.warnings}

    async def publish_agent(self, *, ctx: ControlPlaneContext, agent_id: UUID) -> dict[str, Any]:
        try:
            agent = await self._service(ctx).publish_agent(agent_id, user_id=ctx.user_id)
        except AgentNotFoundError as exc:
            raise not_found(str(exc)) from exc
        except AgentServiceError as exc:
            raise validation(str(exc)) from exc
        tool_binding = await ToolBindingService(self.db).get_agent_tool(agent.id)
        return self.serialize_agent(agent, tool_binding=tool_binding)

    async def start_run(
        self,
        *,
        ctx: ControlPlaneContext,
        agent_id: UUID,
        params: StartAgentRunInput,
    ) -> dict[str, Any]:
        try:
            await self._service(ctx).get_agent(agent_id)
        except AgentNotFoundError as exc:
            raise not_found(str(exc)) from exc
        executor = AgentExecutorService(db=self.db)
        input_context = dict(params.context or {})
        input_context.setdefault("organization_id", str(ctx.organization_id))
        input_context.setdefault("project_id", str(ctx.project_id) if ctx.project_id else None)
        input_context.setdefault("user_id", str(ctx.user_id) if ctx.user_id else None)
        input_context.setdefault("token", ctx.auth_token)
        grants = await FileSpaceService(self.db).resolve_agent_file_space_grants(
            organization_id=ctx.organization_id,
            project_id=ctx.project_id,
            agent_id=agent_id,
        )
        input_context["file_spaces"] = [grant.to_runtime_payload() for grant in grants]
        run_id = await executor.start_run(
            agent_id,
            {
                "messages": list(params.messages or []),
                "input": params.input,
                "thread_id": str(params.thread_id) if params.thread_id else None,
                "context": input_context,
            },
            user_id=ctx.user_id,
            thread_id=params.thread_id,
        )
        run = await self.db.get(AgentRun, run_id)
        return OperationResult(
            operation_id=str(run_id),
            kind="agent_run",
            status=str(getattr(run.status, "value", run.status or "queued")).lower(),
            metadata={"thread_id": str(run.thread_id) if run and run.thread_id else None},
        ).to_dict()

    async def get_run(self, *, ctx: ControlPlaneContext, run_id: UUID) -> dict[str, Any]:
        run = await self.db.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.organization_id == ctx.organization_id,
                AgentRun.project_id == ctx.project_id,
            )
        )
        if run is None:
            raise not_found("Run not found", run_id=str(run_id))
        status = str(getattr(run.status, "value", run.status or "unknown")).lower()
        return OperationResult(
            operation_id=str(run.id),
            kind="agent_run",
            status=status,
            result=run.output_result if isinstance(run.output_result, dict) else None,
            error={"message": run.error_message} if run.error_message else None,
            metadata={
                "thread_id": str(run.thread_id) if run.thread_id else None,
                "checkpoint": run.checkpoint if isinstance(run.checkpoint, dict) else run.checkpoint,
                "run_usage": usage_payload_from_run(run) or {},
                "context_window": ContextWindowService.read_from_run(run),
                "lineage": {
                    "root_run_id": str(run.root_run_id) if run.root_run_id else None,
                    "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
                    "parent_node_id": run.parent_node_id,
                    "depth": int(run.depth or 0),
                    "spawn_key": run.spawn_key,
                    "orchestration_group_id": str(run.orchestration_group_id) if run.orchestration_group_id else None,
                },
            },
        ).to_dict()

    async def list_node_catalog(self, *, ctx: ControlPlaneContext) -> dict[str, Any]:
        register_standard_operators()
        catalog = [
            agent_catalog_item(spec).model_dump(mode="json")
            for spec in AgentOperatorRegistry.list_operators()
            if str(getattr(spec, "category", "")) != "orchestration"
        ]
        catalog.extend(await self._artifact_catalog_items(ctx))
        return {"nodes": catalog}

    async def get_node_schemas(self, *, ctx: ControlPlaneContext, node_types: list[str]) -> dict[str, Any]:
        normalized = [str(item).strip() for item in node_types if str(item).strip()]
        if not normalized:
            raise validation("node_types must be a non-empty array", field="node_types")
        register_standard_operators()
        schemas: dict[str, Any] = {}
        unknown: list[str] = []
        artifact_specs = await self._artifact_node_specs(ctx)
        for node_type in normalized:
            spec = AgentOperatorRegistry.get(node_type)
            if spec is not None:
                schemas[node_type] = agent_node_spec(spec).model_dump(mode="json", exclude_none=True)
                continue
            artifact_spec = artifact_specs.get(node_type)
            if artifact_spec is not None:
                schemas[node_type] = artifact_spec.model_dump(mode="json", exclude_none=True)
                continue
            unknown.append(node_type)
        if unknown:
            raise validation("Unknown node types", field="node_types", unknown=unknown)
        return {"specs": schemas, "instance_contract": agent_instance_contract()}

    async def _artifact_catalog_items(self, ctx: ControlPlaneContext) -> list[dict[str, Any]]:
        return [entry["item"].model_dump(mode="json") for entry in (await self._artifact_specs_with_catalog(ctx)).values()]

    async def _artifact_node_specs(self, ctx: ControlPlaneContext) -> dict[str, Any]:
        return {node_type: pair["spec"] for node_type, pair in (await self._artifact_specs_with_catalog(ctx)).items()}

    async def _artifact_specs_with_catalog(self, ctx: ControlPlaneContext) -> dict[str, dict[str, Any]]:
        artifacts = await ArtifactRegistryService(self.db).list_accessible_artifacts(
            organization_id=ctx.organization_id,
            kind=ArtifactKind.AGENT_NODE,
        )
        result: dict[str, dict[str, Any]] = {}
        for artifact in artifacts:
            revision = artifact.latest_draft_revision or artifact.latest_published_revision
            if revision is None:
                continue
            agent_contract = dict(revision.agent_contract or {}) if revision.agent_contract is not None else {}
            node_ui = dict(agent_contract.get("node_ui") or {}) if isinstance(agent_contract.get("node_ui"), dict) else {}
            input_schema = dict(agent_contract.get("input_schema") or {}) if isinstance(agent_contract.get("input_schema"), dict) else {}
            output_schema = dict(agent_contract.get("output_schema") or {}) if isinstance(agent_contract.get("output_schema"), dict) else {}
            config_schema = dict(revision.config_schema or {}) if revision.config_schema is not None else {}
            spec, item = artifact_node_spec(
                artifact_id=str(artifact.id),
                artifact_revision_id=str(revision.id),
                display_name=str(revision.display_name or artifact.display_name),
                description=str(revision.description or artifact.description or "Artifact-backed node"),
                config_schema=config_schema,
                input_schema=input_schema,
                output_schema=output_schema,
                node_ui=node_ui,
                reads=list(agent_contract.get("state_reads") or []),
                writes=list(agent_contract.get("state_writes") or []),
            )
            result[spec.type] = {"spec": spec, "item": item}
        return result

    @staticmethod
    def serialize_agent(agent: Any, *, view: str = "full", tool_binding: ToolRegistry | None = None) -> dict[str, Any]:
        payload = {
            "id": str(agent.id),
            "organization_id": str(agent.organization_id) if agent.organization_id else None,
            "project_id": str(agent.project_id) if getattr(agent, "project_id", None) else None,
            "name": agent.name,
            "description": agent.description,
            "version": agent.version,
            "status": getattr(agent.status, "value", agent.status or "draft"),
            "is_active": bool(agent.is_active),
            "is_public": bool(agent.is_public),
            "show_in_playground": bool(getattr(agent, "show_in_playground", True)),
            "default_embed_policy_set_id": str(getattr(agent, "default_embed_policy_set_id", "") or "") or None,
            "tool_binding_status": (
                str(getattr(getattr(tool_binding, "status", None), "value", getattr(tool_binding, "status", ""))).lower() or None
            ) if tool_binding is not None else None,
            "is_tool_enabled": tool_binding is not None and bool(getattr(tool_binding, "is_active", False)),
            "created_at": agent.created_at.isoformat() if agent.created_at else None,
            "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
            "published_at": agent.published_at.isoformat() if getattr(agent, "published_at", None) else None,
        }
        if view == "summary":
            return payload
        payload.update(
            {
                "graph_definition": agent.graph_definition or {"nodes": [], "edges": []},
                "memory_config": agent.memory_config or {},
                "execution_constraints": agent.execution_constraints or {},
            }
        )
        return payload
