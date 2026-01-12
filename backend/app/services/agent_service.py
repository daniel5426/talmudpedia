import logging
from datetime import datetime
from typing import Any, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db.postgres.models.agents import Agent, AgentVersion, AgentRun, AgentStatus, RunStatus
from ..agent.graph.compiler import AgentCompiler
from ..agent.graph.schema import AgentGraph

logger = logging.getLogger(__name__)

class AgentServiceError(Exception):
    """Base exception for AgentService."""
    pass

class AgentNotFoundError(AgentServiceError):
    """Raised when an agent is not found."""
    pass


class AgentService:
    """
    Service layer for agent management.
    
    All business logic lives here, keeping routers as thin dispatch layers.
    """
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.compiler = AgentCompiler()

    async def list_agents(
        self, 
        status: Optional[AgentStatus] = None, 
        skip: int = 0, 
        limit: int = 50
    ) -> Tuple[list[Agent], int]:
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

    async def get_agent_by_id(self, agent_id: UUID) -> Agent:
        """Fetch a specific agent by ID."""
        query = select(Agent).where(
            and_(Agent.id == agent_id, Agent.tenant_id == self.tenant_id)
        )
        result = await self.db.execute(query)
        agent = result.scalar_one_or_none()
        
        if not agent:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
            
        return agent

    async def create_agent(self, agent_data: dict[str, Any], user_id: UUID) -> Agent:
        """Create a new agent."""
        agent = Agent(
            tenant_id=self.tenant_id,
            created_by=user_id,
            **agent_data
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def update_agent(self, agent_id: UUID, update_data: dict[str, Any]) -> Agent:
        """Update an existing agent."""
        agent = await self.get_agent_by_id(agent_id)
        
        for key, value in update_data.items():
            if value is not None:
                setattr(agent, key, value)
        
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def publish_agent(self, agent_id: UUID) -> Agent:
        """Publishes the current draft of an agent, creating a version snapshot."""
        agent = await self.get_agent_by_id(agent_id)
        
        # 1. Validate graph before publishing
        graph = AgentGraph(**agent.graph_definition)
        errors = await self.compiler.validate(graph)
        if any(e.severity == "error" for e in errors):
            raise AgentServiceError(f"Cannot publish: Graph validation failed with {len(errors)} errors")
            
        # 2. Create version snapshot
        new_version_num = agent.version + 1
        snapshot = AgentVersion(
            agent_id=agent.id,
            version=agent.version,
            config_snapshot=agent.graph_definition,
            created_at=datetime.utcnow()
        )
        self.db.add(snapshot)
        
        # 3. Update agent status
        agent.status = AgentStatus.PUBLISHED
        agent.version = new_version_num
        agent.published_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def execute_agent(self, agent_id: UUID, input_params: dict[str, Any], user_id: UUID) -> AgentRun:
        """Orchestrates the execution of an agent."""
        agent = await self.get_agent_by_id(agent_id)
        
        # Create run record
        run = AgentRun(
            tenant_id=self.tenant_id,
            agent_id=agent.id,
            user_id=user_id,
            status=RunStatus.RUNNING,
            input_params=input_params,
            started_at=datetime.utcnow()
        )
        self.db.add(run)
        await self.db.flush()
        
        try:
            # 1. Compile agent
            graph = AgentGraph(**agent.graph_definition)
            executable = await self.compiler.compile(graph, config={})
            
            # 2. Run agent (this is where it actually calls LangGraph)
            result = await executable.run(input_params)
            
            # 3. Update run success
            run.status = RunStatus.COMPLETED
            run.output_result = result
            run.completed_at = datetime.utcnow()
            
        except Exception as e:
            logger.exception(f"Error executing agent {agent_id}")
            run.status = RunStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            
        await self.db.commit()
        await self.db.refresh(run)
        return run
