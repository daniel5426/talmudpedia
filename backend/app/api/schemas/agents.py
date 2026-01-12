from typing import Any, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.db.postgres.models.agents import AgentStatus, RunStatus
from .common import PaginationParams


class GraphDefinitionSchema(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class CreateAgentRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    graph_definition: Optional[GraphDefinitionSchema] = None
    memory_config: Optional[dict[str, Any]] = None
    execution_constraints: Optional[dict[str, Any]] = None


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    graph_definition: Optional[GraphDefinitionSchema] = None
    memory_config: Optional[dict[str, Any]] = None
    execution_constraints: Optional[dict[str, Any]] = None
    status: Optional[AgentStatus] = None
    is_active: Optional[bool] = None


class AgentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    graph_definition: GraphDefinitionSchema
    memory_config: dict[str, Any]
    execution_constraints: dict[str, Any]
    status: AgentStatus
    version: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class AgentListResponse(BaseModel):
    agents: list[AgentResponse]
    total: int


class AgentRunResponse(BaseModel):
    id: UUID
    agent_id: UUID
    status: RunStatus
    input_params: dict[str, Any]
    output_result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class ExecuteAgentRequest(BaseModel):
    input: Optional[str] = None
    messages: list[dict[str, Any]] = []
    context: Optional[dict[str, Any]] = None


class ExecuteAgentResponse(BaseModel):
    run_id: str
    output: dict[str, Any]
    steps: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    usage: dict[str, Any]
