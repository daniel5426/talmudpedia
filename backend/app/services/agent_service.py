import logging
import json
from datetime import datetime, timezone
from typing import Any, Optional, Tuple, List, Dict
from uuid import UUID
from dataclasses import dataclass, field

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db.postgres.models.agents import Agent, AgentVersion, AgentRun, AgentStatus, RunStatus
# from ..agent.graph.compiler import AgentCompiler # Mocking compiler for now if not ready, or use it
# from ..agent.graph.schema import AgentGraph

logger = logging.getLogger(__name__)

@dataclass
class CreateAgentData:
    name: str
    slug: str
    description: Optional[str] = None
    graph_definition: Optional[dict] = None
    memory_config: Optional[dict] = None
    execution_constraints: Optional[dict] = None

@dataclass
class UpdateAgentData:
    name: Optional[str] = None
    description: Optional[str] = None
    graph_definition: Optional[dict] = None
    memory_config: Optional[dict] = None
    execution_constraints: Optional[dict] = None

@dataclass
class ExecuteAgentData:
    input: Optional[str] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    context: Optional[Dict[str, Any]] = None

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

class AgentService:
    """
    Service layer for agent management.
    
    All business logic lives here, keeping routers as thin dispatch layers.
    """
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def list_agents(
        self, 
        status: Optional[str] = None, 
        skip: int = 0, 
        limit: int = 50
    ) -> Tuple[List[Agent], int]:
        """List agents for the tenant with pagination and optional status filter."""
        query = select(Agent).where(Agent.tenant_id == self.tenant_id)
        
        if status:
            query = query.where(Agent.status == status)
            
        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)
        
        # Get results
        query = query.offset(skip).limit(limit).order_by(Agent.updated_at.desc())
        result = await self.db.execute(query)
        agents = result.scalars().all()
        
        return list(agents), total

    async def get_agent(self, agent_id: UUID) -> Agent:
        """Fetch a specific agent by ID."""
        query = select(Agent).where(
            and_(Agent.id == agent_id, Agent.tenant_id == self.tenant_id)
        )
        result = await self.db.execute(query)
        agent = result.scalar_one_or_none()
        
        if not agent:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
            
        return agent

    async def create_agent(self, data: CreateAgentData, user_id: Optional[UUID] = None) -> Agent:
        """Create a new agent."""
        # Check if slug exists in this tenant
        existing = await self.db.execute(
            select(Agent).where(and_(Agent.slug == data.slug, Agent.tenant_id == self.tenant_id))
        )
        if existing.scalar_one_or_none():
            raise AgentSlugExistsError(f"Agent with slug '{data.slug}' already exists in this account")

        agent = Agent(
            tenant_id=self.tenant_id,
            name=data.name,
            slug=data.slug,
            description=data.description,
            graph_definition=data.graph_definition or {"nodes": [], "edges": []},
            memory_config=data.memory_config or {},
            execution_constraints=data.execution_constraints or {},
            created_by=user_id,
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def update_agent(self, agent_id: UUID, data: UpdateAgentData) -> Agent:
        """Update an existing agent."""
        agent = await self.get_agent(agent_id)
        
        if agent.status == AgentStatus.published:
            # Maybe allow some updates, but usually draft only
            pass

        if data.name is not None:
            agent.name = data.name
        if data.description is not None:
            agent.description = data.description
        if data.graph_definition is not None:
            agent.graph_definition = data.graph_definition
        if data.memory_config is not None:
            agent.memory_config = data.memory_config
        if data.execution_constraints is not None:
            agent.execution_constraints = data.execution_constraints
        
        await self.db.commit()
        await self.db.refresh(agent)
        return agent
    async def update_graph(self, agent_id: UUID, graph_definition: Dict[str, Any]) -> Agent:
        """Update only the agent graph."""
        agent = await self.get_agent(agent_id)
        agent.graph_definition = graph_definition
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def delete_agent(self, agent_id: UUID) -> bool:
        """Delete an agent."""
        agent = await self.get_agent(agent_id)
        await self.db.delete(agent)
        await self.db.commit()
        return True

    async def validate_agent(self, agent_id: UUID) -> Any:
        """Validate agent graph."""
        # placeholder for validation logic
        class ValidationResult:
            def __init__(self, valid, errors):
                self.valid = valid
                self.errors = errors
        return ValidationResult(True, [])

    async def publish_agent(self, agent_id: UUID) -> Agent:
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
                "context": data.context or {},
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
            last_message = messages[-1] if messages else None
            output_text = ""
            if isinstance(last_message, dict):
                output_text = last_message.get("content", "")

            class ExecResult:
                def __init__(self, run_id, output, steps, messages, usage):
                    self.run_id = run_id
                    self.output = output
                    self.steps = steps
                    self.messages = messages
                    self.usage = usage

            return ExecResult(
                run_id=str(run_id),
                output={"text": output_text},
                steps=[],
                messages=messages,
                usage={"tokens": run.usage_tokens if run else 0},
            )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise AgentServiceError(f"Execution failed: {e}")
