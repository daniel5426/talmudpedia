import logging
import json
from datetime import datetime, timezone
from typing import Any, Optional, Tuple, List, Dict
from uuid import UUID, uuid4
from dataclasses import dataclass, field
from difflib import get_close_matches

from sqlalchemy import select, func, and_, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from pydantic import ValidationError as PydanticValidationError

from ..db.postgres.models.agents import Agent, AgentVersion, AgentRun, AgentTrace, AgentStatus, RunStatus
from app.db.postgres.models.registry import ModelRegistry, ToolRegistry
from app.services.resource_policy_quota_service import ResourcePolicyQuotaExceeded
from app.services.tool_binding_service import ToolBindingService
from app.services.usage_quota_service import QuotaExceededError
from app.services.prompt_reference_resolver import PromptReferenceError, PromptReferenceResolver
from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph
from app.agent.registry import AgentOperatorRegistry
from app.graph_authoring import (
    build_authoring_issue,
    collect_agent_authoring_issues,
    critical_agent_write_issues,
    dedupe_issues,
    normalize_agent_graph_definition,
    normalize_agent_node_type,
)
# from ..agent.graph.compiler import AgentCompiler # Mocking compiler for now if not ready, or use it
# from ..agent.graph.schema import AgentGraph

logger = logging.getLogger(__name__)

@dataclass
class CreateAgentData:
    name: str
    description: Optional[str] = None
    graph_definition: dict = field(default_factory=dict)
    memory_config: Optional[dict] = None
    execution_constraints: Optional[dict] = None
    show_in_playground: bool = True

@dataclass
class UpdateAgentData:
    name: Optional[str] = None
    description: Optional[str] = None
    graph_definition: Optional[dict] = None
    memory_config: Optional[dict] = None
    execution_constraints: Optional[dict] = None
    show_in_playground: Optional[bool] = None

@dataclass
class ExecuteAgentData:
    input: Optional[str] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    state: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class AgentValidationResult:
    valid: bool
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)


class AgentServiceError(Exception):
    """Base exception for AgentService."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class AgentNotFoundError(AgentServiceError):
    """Raised when an agent is not found."""
    pass

class AgentSlugExistsError(AgentServiceError):
    """Raised when an agent slug already exists."""
    pass

class AgentPublishedError(AgentServiceError):
    """Raised when operation is forbidden on a published agent."""
    pass

class AgentNotPublishedError(AgentServiceError):
    """Raised when operation is forbidden on a non-published agent."""
    pass


class AgentGraphValidationError(AgentServiceError):
    """Raised when graph_definition cannot be persisted safely."""

    def __init__(self, errors: List[Dict[str, Any]]):
        super().__init__("Graph write rejected")
        self.errors = errors


class AgentInputValidationError(AgentServiceError):
    """Raised when agent create/update input is invalid."""


class AgentService:
    """
    Service layer for agent management.
    
    All business logic lives here, keeping routers as thin dispatch layers.
    """
    
    def __init__(self, db: AsyncSession, organization_id: UUID, project_id: UUID | None = None):
        self.db = db
        self.organization_id = organization_id
        self.project_id = project_id

    def _require_project_id(self) -> UUID:
        if self.project_id is None:
            raise AgentInputValidationError("Active project context is required")
        return self.project_id

    @staticmethod
    def _internal_row_key(prefix: str = "agent") -> str:
        return f"{prefix}-{uuid4().hex}"

    @staticmethod
    def _normalize_graph_errors(raw_errors: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for err in raw_errors:
            if hasattr(err, "model_dump"):
                payload = err.model_dump()
            elif isinstance(err, dict):
                payload = dict(err)
            else:
                payload = {"message": str(err)}
            normalized.append(
                {
                    "node_id": payload.get("node_id"),
                    "edge_id": payload.get("edge_id"),
                    "message": str(payload.get("message") or "Graph validation failed"),
                    "severity": str(payload.get("severity") or "error"),
                }
            )
        return normalized

    @staticmethod
    def _normalize_node_type(node_type: Any) -> str:
        return normalize_agent_node_type(node_type)

    @staticmethod
    def _build_rich_validation_issue(
        *,
        code: str,
        message: str,
        severity: str,
        node_id: Optional[str] = None,
        edge_id: Optional[str] = None,
        path: Optional[str] = None,
        expected: Any = None,
        actual: Any = None,
        suggestions: Optional[List[str]] = None,
        suggested_value: Any = None,
        repair_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        return build_authoring_issue(
            code=code,
            message=message,
            severity=severity,
            node_id=node_id,
            edge_id=edge_id,
            path=path,
            expected=expected,
            actual=actual,
            suggestions=suggestions if isinstance(suggestions, list) else None,
            suggested_value=suggested_value,
            repair_hint=repair_hint,
        )

    @staticmethod
    def _derive_error_code(message: str) -> str:
        lowered = str(message or "").lower()
        if "exactly one start node" in lowered:
            return "GRAPH_START_NODE_COUNT_INVALID"
        if "at least one end node" in lowered:
            return "GRAPH_END_NODE_MISSING"
        if "unreachable from start node" in lowered:
            return "GRAPH_UNREACHABLE_NODE"
        if "unknown node type" in lowered:
            return "UNKNOWN_NODE_TYPE"
        if "config error" in lowered:
            return "NODE_CONFIG_INVALID"
        if "invalid branch handle" in lowered:
            return "INVALID_BRANCH_HANDLE"
        if "missing branch edges" in lowered:
            return "MISSING_BRANCH_EDGES"
        if "missing source_handle" in lowered:
            return "MISSING_SOURCE_HANDLE"
        if "duplicate branch handle" in lowered:
            return "DUPLICATE_BRANCH_HANDLE"
        if "graphspec v2 orchestration" in lowered:
            return "GRAPHSPEC_V2_ORCHESTRATION_ERROR"
        return "GRAPH_VALIDATION_ERROR"

    async def _model_exists(self, model_ref: str) -> bool:
        if not model_ref:
            return False
        try:
            parsed_model_id = UUID(str(model_ref))
        except Exception:
            return False
        res = await self.db.execute(
            select(ModelRegistry.id).where(
                ModelRegistry.id == parsed_model_id,
                ModelRegistry.is_active.is_(True),
                or_(ModelRegistry.organization_id == self.organization_id, ModelRegistry.organization_id.is_(None)),
            ).limit(1)
        )
        return res.scalar_one_or_none() is not None

    async def _tool_exists(self, tool_ref: str) -> bool:
        if not tool_ref:
            return False
        try:
            tool_uuid = UUID(str(tool_ref))
        except Exception:
            return False
        res = await self.db.execute(
            select(ToolRegistry.id).where(
                ToolRegistry.id == tool_uuid,
                ToolRegistry.is_active.is_(True),
                or_(
                    ToolRegistry.organization_id.is_(None),
                    and_(
                        ToolRegistry.organization_id == self.organization_id,
                        ToolRegistry.project_id == self._require_project_id(),
                    ),
                ),
            ).limit(1)
        )
        return res.scalar_one_or_none() is not None

    async def _collect_runtime_reference_issues(
        self,
        graph_definition: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        nodes = graph_definition.get("nodes") if isinstance(graph_definition, dict) else []
        if not isinstance(nodes, list):
            return issues

        model_required_node_types = {"agent", "classify"}

        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id")) if node.get("id") is not None else None
            node_type = self._normalize_node_type(node.get("type"))
            config = node.get("config") if isinstance(node.get("config"), dict) else {}

            if node_type in model_required_node_types:
                model_ref = str(config.get("model_id") or "").strip()
                if model_ref:
                    exists = await self._model_exists(model_ref)
                    if not exists:
                        issues.append(
                            self._build_rich_validation_issue(
                                code="MODEL_NOT_FOUND",
                                message=f"Referenced model '{model_ref}' was not found in organization/global active models",
                                severity="error",
                                node_id=node_id,
                                path=f"/nodes/{idx}/config/model_id",
                                expected="Existing active model id in organization or global scope",
                                actual=model_ref,
                                suggestions=None,
                            )
                        )

            if node_type == "tool":
                tool_ref = str(config.get("tool_id") or "").strip()
                if tool_ref:
                    exists = await self._tool_exists(tool_ref)
                    if not exists:
                        issues.append(
                            self._build_rich_validation_issue(
                                code="TOOL_NOT_FOUND",
                                message=f"Referenced tool '{tool_ref}' was not found in organization/global active tools",
                                severity="error",
                                node_id=node_id,
                                path=f"/nodes/{idx}/config/tool_id",
                                expected="Existing active tool id in organization or global scope",
                                actual=tool_ref,
                                suggestions=None,
                            )
                        )
        return issues

    async def _validate_graph_for_write(
        self,
        graph_definition: Any,
        *,
        agent_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        if not isinstance(graph_definition, dict):
            raise AgentGraphValidationError(
                [
                    self._build_rich_validation_issue(
                        code="INVALID_GRAPH_DEFINITION",
                        message="graph_definition must be an object",
                        severity="error",
                        expected="object",
                        actual=type(graph_definition).__name__,
                    )
                ]
            )

        try:
            normalized_graph = normalize_agent_graph_definition(graph_definition)
        except PydanticValidationError as exc:
            raise AgentGraphValidationError(
                [
                    self._build_rich_validation_issue(
                        code="INVALID_GRAPH_SCHEMA",
                        message=f"Invalid graph schema: {exc}",
                        severity="error",
                        expected="AgentGraph schema compliant object",
                        actual="schema_validation_failed",
                    )
                ]
            ) from exc

        write_issues = critical_agent_write_issues(collect_agent_authoring_issues(normalized_graph))
        if write_issues:
            raise AgentGraphValidationError(write_issues)

        try:
            await PromptReferenceResolver(self.db, self.organization_id).validate_graph_definition(normalized_graph)
        except PromptReferenceError as exc:
            raise AgentGraphValidationError(
                [
                    self._build_rich_validation_issue(
                        code="PROMPT_REFERENCE_INVALID",
                        message=str(exc),
                        severity="error",
                        repair_hint="Fix the prompt reference or remove it from the graph before saving.",
                    )
                ]
            ) from exc

        # Persistence rejects only illegal graph documents and explicit bad references.
        reference_issues = await self._collect_runtime_reference_issues(normalized_graph)
        critical_errors = [item for item in reference_issues if item.get("severity") == "error"]
        if critical_errors:
            raise AgentGraphValidationError(critical_errors)
        return normalized_graph

    async def _build_validation_result_for_graph(
        self,
        graph_definition: Any,
        *,
        agent_id: Optional[UUID] = None,
    ) -> AgentValidationResult:
        if not isinstance(graph_definition, dict):
            issue = self._build_rich_validation_issue(
                code="INVALID_GRAPH_DEFINITION",
                message="graph_definition must be an object",
                severity="error",
                expected="object",
                actual=type(graph_definition).__name__,
            )
            return AgentValidationResult(valid=False, errors=[issue], warnings=[])

        nodes = graph_definition.get("nodes") if isinstance(graph_definition.get("nodes"), list) else []
        node_index_by_id: Dict[str, int] = {}
        for idx, node in enumerate(nodes):
            if isinstance(node, dict) and node.get("id") is not None:
                node_index_by_id[str(node.get("id"))] = idx

        from app.agent.executors.standard import register_standard_operators
        register_standard_operators()
        operator_types = [spec.type for spec in AgentOperatorRegistry.list_operators()]

        issues: List[Dict[str, Any]] = []
        try:
            normalized_graph = normalize_agent_graph_definition(graph_definition)
            graph = AgentGraph(**normalized_graph)
        except PydanticValidationError as exc:
            issues.append(
                self._build_rich_validation_issue(
                    code="INVALID_GRAPH_SCHEMA",
                    message=f"Invalid graph schema: {exc}",
                    severity="error",
                    expected="AgentGraph schema compliant object",
                    actual="schema_validation_failed",
                )
            )
            return AgentValidationResult(valid=False, errors=issues, warnings=[])

        issues.extend(collect_agent_authoring_issues(normalized_graph))

        compiler = AgentCompiler(db=self.db, organization_id=self.organization_id)
        try:
            raw_errors = await compiler.validate(graph, agent_id=agent_id)
        except Exception as exc:
            raw_errors = [
                self._build_rich_validation_issue(
                    code="GRAPH_ANALYSIS_FAILED",
                    message=str(exc),
                    severity="error",
                )
            ]
        for raw in raw_errors:
            payload = raw.model_dump() if hasattr(raw, "model_dump") else (dict(raw) if isinstance(raw, dict) else {"message": str(raw)})
            node_id = str(payload.get("node_id")) if payload.get("node_id") is not None else None
            message = str(payload.get("message") or "Graph validation failed")
            severity = str(payload.get("severity") or "error")
            code = self._derive_error_code(message)

            path: Optional[str] = None
            expected: Any = None
            actual: Any = None
            suggestions: Optional[List[str]] = None

            if node_id is not None and node_id in node_index_by_id:
                path = f"/nodes/{node_index_by_id[node_id]}"

            if code == "UNKNOWN_NODE_TYPE" and node_id and node_id in node_index_by_id:
                node_idx = node_index_by_id[node_id]
                candidate = None
                if 0 <= node_idx < len(nodes) and isinstance(nodes[node_idx], dict):
                    candidate = str(nodes[node_idx].get("type") or "")
                    path = f"/nodes/{node_idx}/type"
                    actual = candidate
                expected = "Registered node type"
                suggestions = get_close_matches(candidate or "", operator_types, n=5, cutoff=0.35) or None

            issues.append(
                self._build_rich_validation_issue(
                    code=code,
                    message=message,
                    severity=severity,
                    node_id=node_id,
                    edge_id=str(payload.get("edge_id")) if payload.get("edge_id") is not None else None,
                    path=path,
                    expected=expected,
                    actual=actual,
                    suggestions=suggestions,
                    suggested_value=suggestions[0] if suggestions else None,
                    repair_hint="Fix the graph node type or config and validate again." if code != "GRAPH_ANALYSIS_FAILED" else None,
                )
            )

        issues.extend(await self._collect_runtime_reference_issues(normalized_graph))
        issues = dedupe_issues(issues)

        errors = [item for item in issues if str(item.get("severity") or "").lower() == "error"]
        warnings = [item for item in issues if str(item.get("severity") or "").lower() != "error"]
        return AgentValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    async def list_agents(
        self, 
        status: Optional[str] = None, 
        skip: int = 0, 
        limit: int = 50,
        compact: bool = False,
    ) -> Tuple[List[Agent], int]:
        """List agents for the organization with pagination and optional status filter."""
        filters = [Agent.organization_id == self.organization_id, Agent.project_id == self._require_project_id()]
        
        if status:
            filters.append(Agent.status == status)

        # Count total
        count_query = select(func.count()).select_from(Agent).where(*filters)
        total = await self.db.scalar(count_query)
        
        # Get results
        query = (
            select(Agent)
            .where(*filters)
            .order_by(Agent.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if compact:
            # Exclude large JSON columns used mainly by builder/execution flows.
            query = query.options(
                load_only(
                    Agent.id,
                    Agent.organization_id,
                    Agent.project_id,
                    Agent.name,
                    Agent.description,
                    Agent.version,
                    Agent.status,
                    Agent.created_at,
                    Agent.updated_at,
                    Agent.published_at,
                    Agent.is_active,
                    Agent.is_public,
                    Agent.show_in_playground,
                    Agent.default_embed_policy_set_id,
                )
            )
        result = await self.db.execute(query)
        agents = result.scalars().all()
        
        return list(agents), total

    async def get_agent(self, agent_id: UUID) -> Agent:
        """Fetch a specific agent by ID."""
        query = select(Agent).where(
            and_(Agent.id == agent_id, Agent.organization_id == self.organization_id, Agent.project_id == self._require_project_id())
        )
        result = await self.db.execute(query)
        agent = result.scalar_one_or_none()
        
        if not agent:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
            
        return agent

    async def create_agent(self, data: CreateAgentData, user_id: Optional[UUID] = None) -> Agent:
        """Create a new agent."""
        data.name = str(data.name or "").strip()
        if not data.name:
            raise AgentInputValidationError("Agent name is required")
        if not data.graph_definition:
            raise AgentGraphValidationError(
                [
                    {
                        "node_id": None,
                        "edge_id": None,
                        "message": "graph_definition is required",
                        "severity": "error",
                    }
                ]
            )

        validated_graph = await self._validate_graph_for_write(data.graph_definition)
        slug = self._internal_row_key("agent")
        while (
            await self.db.execute(
                select(Agent.id).where(and_(Agent.slug == slug, Agent.organization_id == self.organization_id)).limit(1)
            )
        ).scalar_one_or_none() is not None:
            slug = self._internal_row_key("agent")

        agent = Agent(
            organization_id=self.organization_id,
            project_id=self._require_project_id(),
            name=data.name,
            slug=slug,
            description=data.description,
            graph_definition=validated_graph,
            memory_config=data.memory_config or {},
            execution_constraints=data.execution_constraints or {},
            show_in_playground=bool(data.show_in_playground),
            created_by=user_id,
        )
        self.db.add(agent)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def update_agent(self, agent_id: UUID, data: UpdateAgentData, user_id: Optional[UUID] = None) -> Agent:
        """Update an existing agent."""
        agent = await self.get_agent(agent_id)
        
        if agent.status == AgentStatus.published:
            # Maybe allow some updates, but usually draft only
            pass

        if data.name is not None:
            if not str(data.name).strip():
                raise AgentInputValidationError("Agent name cannot be blank")
            agent.name = data.name
        if data.description is not None:
            agent.description = data.description
        if data.graph_definition is not None:
            agent.graph_definition = await self._validate_graph_for_write(
                data.graph_definition,
                agent_id=agent.id,
            )
        if data.memory_config is not None:
            agent.memory_config = data.memory_config
        if data.execution_constraints is not None:
            agent.execution_constraints = data.execution_constraints
        if data.show_in_playground is not None:
            agent.show_in_playground = bool(data.show_in_playground)
        await ToolBindingService(self.db).sync_exported_agent_tool_binding(
            agent=agent,
            created_by=user_id,
        )
        
        await self.db.commit()
        await self.db.refresh(agent)
        return agent
    async def update_graph(self, agent_id: UUID, graph_definition: Dict[str, Any]) -> Agent:
        """Update only the agent graph."""
        agent = await self.get_agent(agent_id)
        agent.graph_definition = await self._validate_graph_for_write(
            graph_definition,
            agent_id=agent.id,
        )
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def delete_agent(self, agent_id: UUID) -> bool:
        """Delete an agent."""
        await self.get_agent(agent_id)
        await ToolBindingService(self.db).delete_agent_tool_binding(agent_id)

        # Use explicit SQL deletes to avoid ORM relationship-loading on agent_runs.
        # This keeps deletion compatible with DBs that are missing newer run-lineage columns.
        run_ids_subquery = select(AgentRun.id).where(
            and_(
                AgentRun.agent_id == agent_id,
                AgentRun.organization_id == self.organization_id,
                AgentRun.project_id == self._require_project_id(),
            )
        )

        await self.db.execute(delete(AgentVersion).where(AgentVersion.agent_id == agent_id))
        await self.db.execute(delete(AgentTrace).where(AgentTrace.run_id.in_(run_ids_subquery)))
        await self.db.execute(delete(AgentRun).where(AgentRun.id.in_(run_ids_subquery)))
        await self.db.execute(
            delete(Agent).where(
                and_(
                    Agent.id == agent_id,
                    Agent.organization_id == self.organization_id,
                    Agent.project_id == self._require_project_id(),
                )
            )
        )
        await self.db.commit()
        return True

    async def validate_agent(self, agent_id: UUID) -> AgentValidationResult:
        """Validate persisted agent graph using compiler + organization resource checks."""
        agent = await self.get_agent(agent_id)
        graph_definition = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
        return await self._build_validation_result_for_graph(
            graph_definition,
            agent_id=agent.id,
        )

    async def publish_agent(self, agent_id: UUID, user_id: Optional[UUID] = None) -> Agent:
        """Publishes the current draft of an agent, creating a version snapshot."""
        agent = await self.get_agent(agent_id)
        
        # Snapshot
        snapshot = AgentVersion(
            agent_id=agent.id,
            version=agent.version,
            config_snapshot=agent.graph_definition,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(snapshot)
        
        # Update agent status
        agent.status = AgentStatus.published
        agent.version += 1
        agent.published_at = datetime.now(timezone.utc)
        await ToolBindingService(self.db).sync_exported_agent_tool_binding(
            agent=agent,
            created_by=user_id,
        )
        
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def list_versions(self, agent_id: UUID) -> List[AgentVersion]:
        """List versions of an agent."""
        query = select(AgentVersion).where(AgentVersion.agent_id == agent_id).order_by(AgentVersion.version.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_version(self, agent_id: UUID, version: int) -> Optional[AgentVersion]:
        """Get a specific version."""
        query = select(AgentVersion).where(
            and_(AgentVersion.agent_id == agent_id, AgentVersion.version == version)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def execute_agent(self, agent_id: UUID, data: ExecuteAgentData, user_id: Optional[UUID] = None) -> Any:
        """Orchestrates the execution of an agent."""
        agent = await self.get_agent(agent_id)

        from app.agent.execution.service import AgentExecutorService
        from app.agent.execution.types import ExecutionMode

        try:
            input_state = {
                "messages": data.messages or [],
                "input": data.input,
                "state": data.state or {},
                "context": data.context or {},
                "workflow_input": {"text": data.input or "", "input_as_text": data.input or ""},
            }
            if data.input:
                input_state["messages"].append({"role": "user", "content": data.input})

            executor = AgentExecutorService(db=self.db)
            run_id = await executor.start_run(
                agent_id=agent.id,
                input_params=input_state,
                user_id=user_id,
                background=False,
                mode=ExecutionMode.PRODUCTION,
                requested_scopes=(data.context or {}).get("requested_scopes") if isinstance(data.context, dict) else None,
            )

            async for _ in executor.run_and_stream(run_id, self.db, mode=ExecutionMode.PRODUCTION):
                pass

            run = await self.db.get(AgentRun, run_id)
            result_state = run.output_result or {}
            messages = result_state.get("messages", [])
            final_output = result_state.get("final_output")
            output_text = final_output if isinstance(final_output, str) else ""

            class ExecResult:
                def __init__(self, run_id, output, steps, messages, usage):
                    self.run_id = run_id
                    self.output = output
                    self.steps = steps
                    self.messages = messages
                    self.usage = usage

            return ExecResult(
                run_id=str(run_id),
                output={"value": final_output, "text": output_text},
                steps=[],
                messages=messages,
                usage={"tokens": run.usage_tokens if run else 0},
            )

        except (QuotaExceededError, ResourcePolicyQuotaExceeded):
            raise
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise AgentServiceError(f"Execution failed: {e}")
