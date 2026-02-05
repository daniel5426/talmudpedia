"""
Stats API Schemas
Pydantic models for stats endpoint responses.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from uuid import UUID


# --- Common Types ---

class DailyDataPoint(BaseModel):
    """Single data point for time series charts."""
    date: str  # YYYY-MM-DD
    value: float


class TrendInfo(BaseModel):
    """Trend comparison vs previous period."""
    current: float
    previous: float
    change_pct: float


class TopUserSummary(BaseModel):
    """Summary for top users by activity."""
    user_id: UUID
    email: str
    full_name: Optional[str]
    count: int


class ModelUsageSummary(BaseModel):
    """Usage summary for a model."""
    model_name: str
    message_count: int
    token_count: int


class StatusBreakdownSummary(BaseModel):
    """Generic status breakdown summary."""
    status: str
    count: int


class PipelineUsageSummary(BaseModel):
    """Usage summary for a pipeline."""
    id: UUID
    name: str
    run_count: int
    failed_count: int
    failure_rate: float
    last_run_at: Optional[datetime]


class AgentUsageSummary(BaseModel):
    """Usage summary for an agent."""
    id: UUID
    name: str
    slug: str
    run_count: int
    tokens_used: int


class AgentFailureSummary(BaseModel):
    """Failure summary for agent runs."""
    run_id: UUID
    agent_id: UUID
    agent_name: str
    status: str
    user_email: Optional[str]
    error_message: Optional[str]
    created_at: datetime


class ProviderUsageSummary(BaseModel):
    """Usage summary for model providers."""
    provider: str
    count: int


class JobFailureSummary(BaseModel):
    """Failure summary for pipeline jobs."""
    id: UUID
    pipeline_name: str
    status: str
    error_message: Optional[str]
    created_at: datetime


# --- Overview Stats ---

class OverviewStats(BaseModel):
    """Cross-platform KPIs for the Overview tab."""
    # User metrics
    total_users: int
    active_users: int  # Users with activity in the period
    
    # Chat metrics
    total_chats: int
    total_messages: int
    
    # Token metrics
    total_tokens: int
    estimated_spend_usd: float

    # Period metrics
    new_users: int
    avg_messages_per_chat: float
    
    # Execution metrics
    agent_runs: int
    agent_runs_failed: int
    pipeline_jobs: int
    pipeline_jobs_failed: int
    
    # Time series data
    tokens_by_day: list[DailyDataPoint]
    spend_by_day: list[DailyDataPoint]
    daily_active_users: list[DailyDataPoint]
    messages_by_role: dict[str, int]
    top_users: list[TopUserSummary]
    top_models: list[ModelUsageSummary]


# --- RAG Stats ---

class KnowledgeStoreSummary(BaseModel):
    """Summary of a knowledge store."""
    id: UUID
    name: str
    status: str
    document_count: int
    chunk_count: int
    storage_backend: str
    last_synced_at: Optional[datetime]


class PipelineSummary(BaseModel):
    """Summary of a RAG pipeline."""
    id: UUID
    name: str
    pipeline_type: str
    is_active: bool
    last_run_at: Optional[datetime]
    run_count: int


class JobSummary(BaseModel):
    """Summary of a pipeline job."""
    id: UUID
    pipeline_name: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    chunk_count: int


class RAGStats(BaseModel):
    """RAG-specific stats for the RAG tab."""
    # Counts
    knowledge_store_count: int
    pipeline_count: int
    total_chunks: int

    # Breakdown
    stores_by_status: dict[str, int]
    pipelines_by_type: dict[str, int]
    avg_job_duration_ms: Optional[float]
    p95_job_duration_ms: Optional[float]
    
    # Lists
    knowledge_stores: list[KnowledgeStoreSummary]
    pipelines: list[PipelineSummary]
    recent_jobs: list[JobSummary]
    top_pipelines: list[PipelineUsageSummary]
    recent_failed_jobs: list[JobFailureSummary]
    
    # Time series
    jobs_by_day: list[DailyDataPoint]
    jobs_by_status: dict[str, int]


# --- Agent Stats ---

class AgentSummary(BaseModel):
    """Summary of an agent."""
    id: UUID
    name: str
    slug: str
    status: str
    run_count: int
    failed_count: int
    last_run_at: Optional[datetime]
    avg_duration_ms: Optional[float]


class AgentStats(BaseModel):
    """Agent-specific stats for the Agents tab."""
    # Counts
    agent_count: int
    total_runs: int
    total_failed: int
    failure_rate: float

    # Performance
    avg_run_duration_ms: Optional[float]
    p95_run_duration_ms: Optional[float]
    avg_queue_time_ms: Optional[float]
    tokens_used_total: int
    
    # Lists
    agents: list[AgentSummary]
    top_agents: list[AgentSummary]  # By run count
    top_agents_by_tokens: list[AgentUsageSummary]
    top_users_by_runs: list[TopUserSummary]
    recent_failures: list[AgentFailureSummary]
    
    # Time series
    runs_by_day: list[DailyDataPoint]
    runs_by_status: dict[str, int]
    tokens_by_day: list[DailyDataPoint]


# --- Resource Stats ---

class ToolSummary(BaseModel):
    """Summary of a tool."""
    id: UUID
    name: str
    implementation_type: str
    status: str
    # Usage tracking would require additional logging


class ModelSummary(BaseModel):
    """Summary of a model."""
    id: UUID
    name: str
    slug: str
    capability_type: str
    status: str
    provider_count: int


class ArtifactSummary(BaseModel):
    """Summary of a custom operator/artifact."""
    id: UUID
    name: str
    category: str
    version: str
    is_active: bool


class ResourceStats(BaseModel):
    """Resource stats for the Resources tab."""
    # Counts
    tool_count: int
    model_count: int
    artifact_count: int

    # Breakdown
    tools_by_status: dict[str, int]
    tools_by_type: dict[str, int]
    models_by_capability: dict[str, int]
    models_by_status: dict[str, int]
    provider_bindings_by_provider: list[ProviderUsageSummary]
    artifacts_by_category: dict[str, int]
    artifacts_by_active: dict[str, int]
    
    # Lists
    tools: list[ToolSummary]
    models: list[ModelSummary]
    artifacts: list[ArtifactSummary]


# --- Combined Response ---

class StatsResponse(BaseModel):
    """Combined stats response based on section parameter."""
    section: str
    period_days: int
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    
    # One of these will be populated based on section
    overview: Optional[OverviewStats] = None
    rag: Optional[RAGStats] = None
    agents: Optional[AgentStats] = None
    resources: Optional[ResourceStats] = None
