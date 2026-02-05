"""
Stats API Router
Provides comprehensive platform statistics for the admin stats dashboard.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional, Literal
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, func, desc, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.session import get_db
from app.api.routers.auth import get_current_user
from app.db.postgres.models.identity import User, OrgMembership, OrgRole, Tenant
from app.db.postgres.models.chat import Chat, Message, MessageRole
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus, AgentStatus
from app.db.postgres.models.rag import (
    KnowledgeStore, RAGPipeline, VisualPipeline, ExecutablePipeline, 
    PipelineJob, PipelineJobStatus, PipelineType
)
from app.db.postgres.models.registry import (
    ToolRegistry, ModelRegistry, ModelProviderBinding, ToolStatus
)
from app.db.postgres.models.operators import CustomOperator

from app.api.schemas.stats import (
    StatsResponse, OverviewStats, RAGStats, AgentStats, ResourceStats,
    DailyDataPoint, KnowledgeStoreSummary, PipelineSummary, JobSummary,
    AgentSummary, ToolSummary, ModelSummary, ArtifactSummary,
    TopUserSummary, ModelUsageSummary, PipelineUsageSummary, AgentUsageSummary,
    AgentFailureSummary, ProviderUsageSummary, JobFailureSummary
)

router = APIRouter(prefix="/stats", tags=["stats"])


# --- Dependencies ---

async def get_tenant_context(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get tenant context for the current user."""
    if current_user.role == "admin":
        # System admin can see all - but for this endpoint we want their first tenant
        result = await db.execute(
            select(OrgMembership).where(OrgMembership.user_id == current_user.id).limit(1)
        )
        membership = result.scalar_one_or_none()
        return {"user": current_user, "tenant_id": membership.tenant_id if membership else None}

    # Get tenant from org membership
    result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == current_user.id).limit(1)
    )
    membership = result.scalar_one_or_none()
    
    if membership and membership.role in [OrgRole.owner, OrgRole.admin]:
        return {"user": current_user, "tenant_id": membership.tenant_id}
        
    raise HTTPException(status_code=403, detail="Not authorized")


# --- Helpers ---

def parse_iso_datetime(value: str, end_of_day: bool = False) -> datetime:
    """Parse ISO date/datetime strings into timezone-aware UTC datetimes."""
    dt = None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.strptime(value.split("T")[0], "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if end_of_day and len(value) <= 10:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=0)
    if not end_of_day and len(value) <= 10:
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt


def get_period_range(
    days: int,
    start_date: Optional[str],
    end_date: Optional[str]
) -> tuple[datetime, datetime]:
    """Get start and end dates for the period, preferring explicit range."""
    now = datetime.now(timezone.utc)
    if start_date or end_date:
        parsed_start = parse_iso_datetime(start_date, end_of_day=False) if start_date else None
        parsed_end = parse_iso_datetime(end_date, end_of_day=True) if end_date else None
        if parsed_start and not parsed_end:
            parsed_end = now
        if parsed_end and not parsed_start:
            parsed_start = parsed_end - timedelta(days=days)
        start, end = parsed_start, parsed_end
    else:
        end = now
        start = now - timedelta(days=days)

    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    if end - start > timedelta(days=90):
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")
    return start, end


def fill_daily_data(
    data_map: dict[str, float],
    start: datetime,
    end: datetime
) -> list[DailyDataPoint]:
    """Fill in missing days with zero values."""
    full_data = []
    current = start.date()
    end_date = end.date()
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        full_data.append(DailyDataPoint(
            date=date_str,
            value=data_map.get(date_str, 0.0)
        ))
        current += timedelta(days=1)
    return full_data


async def get_daily_data(
    db: AsyncSession,
    table,
    date_column,
    count_expr,
    tenant_id: UUID,
    start: datetime,
    end: datetime
) -> list[DailyDataPoint]:
    """Get daily aggregated data for a table."""
    query = (
        select(
            func.date(date_column).label('date'),
            count_expr.label('value')
        )
        .where(and_(
            date_column >= start,
            date_column <= end
        ))
        .group_by(func.date(date_column))
        .order_by(func.date(date_column))
    )
    
    if hasattr(table, 'tenant_id') and tenant_id:
        query = query.where(table.tenant_id == tenant_id)
    
    result = await db.execute(query)
    data_map = {r.date.strftime("%Y-%m-%d"): float(r.value) for r in result.all()}
    return fill_daily_data(data_map, start, end)


# --- Section Handlers ---

async def get_overview_stats(
    db: AsyncSession,
    tenant_id: UUID,
    start: datetime,
    end: datetime
) -> OverviewStats:
    """Get overview statistics."""
    
    # Total users in tenant
    q_users = select(func.count(User.id)).join(OrgMembership).where(OrgMembership.tenant_id == tenant_id)
    total_users = (await db.execute(q_users)).scalar() or 0
    
    # Active users (with chats in period)
    q_active = (
        select(func.count(func.distinct(Chat.user_id)))
        .where(and_(
            Chat.tenant_id == tenant_id,
            Chat.updated_at >= start,
            Chat.updated_at <= end
        ))
    )
    active_users = (await db.execute(q_active)).scalar() or 0
    
    # Total chats in period
    q_chats = select(func.count(Chat.id)).where(and_(
        Chat.tenant_id == tenant_id,
        Chat.created_at >= start,
        Chat.created_at <= end
    ))
    total_chats = (await db.execute(q_chats)).scalar() or 0
    
    # Total messages in period (via join)
    q_messages = (
        select(func.count(Message.id))
        .join(Chat)
        .where(and_(
            Chat.tenant_id == tenant_id,
            Message.created_at >= start,
            Message.created_at <= end
        ))
    )
    total_messages = (await db.execute(q_messages)).scalar() or 0
    
    # Total tokens (sum token_count from messages in period)
    q_tokens = (
        select(func.coalesce(func.sum(Message.token_count), 0))
        .join(Chat)
        .where(and_(
            Chat.tenant_id == tenant_id,
            Message.created_at >= start,
            Message.created_at <= end
        ))
    )
    total_tokens = (await db.execute(q_tokens)).scalar() or 0
    
    # Agent runs
    q_runs = (
        select(func.count(AgentRun.id))
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
    )
    agent_runs = (await db.execute(q_runs)).scalar() or 0
    
    # Failed agent runs
    q_failed_runs = (
        select(func.count(AgentRun.id))
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.status == RunStatus.failed,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
    )
    agent_runs_failed = (await db.execute(q_failed_runs)).scalar() or 0
    
    # Pipeline jobs
    q_jobs = (
        select(func.count(PipelineJob.id))
        .where(and_(
            PipelineJob.tenant_id == tenant_id,
            PipelineJob.created_at >= start,
            PipelineJob.created_at <= end
        ))
    )
    pipeline_jobs = (await db.execute(q_jobs)).scalar() or 0
    
    # Failed pipeline jobs
    q_failed_jobs = (
        select(func.count(PipelineJob.id))
        .where(and_(
            PipelineJob.tenant_id == tenant_id,
            PipelineJob.status == PipelineJobStatus.FAILED,
            PipelineJob.created_at >= start,
            PipelineJob.created_at <= end
        ))
    )
    pipeline_jobs_failed = (await db.execute(q_failed_jobs)).scalar() or 0

    # New users in period
    q_new_users = (
        select(func.count(User.id))
        .join(OrgMembership)
        .where(and_(
            OrgMembership.tenant_id == tenant_id,
            User.created_at >= start,
            User.created_at <= end
        ))
    )
    new_users = (await db.execute(q_new_users)).scalar() or 0

    avg_messages_per_chat = round(total_messages / total_chats, 2) if total_chats > 0 else 0.0
    
    # Estimated spend (simplified - would need cost lookup in real implementation)
    # For now: $0.002 per 1K tokens as rough estimate
    estimated_spend = (total_tokens / 1000) * 0.002
    
    # Daily tokens
    q_daily_tokens = (
        select(
            func.date(Message.created_at).label('date'),
            func.coalesce(func.sum(Message.token_count), 0).label('value')
        )
        .join(Chat)
        .where(and_(
            Chat.tenant_id == tenant_id,
            Message.created_at >= start,
            Message.created_at <= end
        ))
        .group_by(func.date(Message.created_at))
        .order_by(func.date(Message.created_at))
    )
    tokens_result = await db.execute(q_daily_tokens)
    tokens_map = {r.date.strftime("%Y-%m-%d"): float(r.value) for r in tokens_result.all()}
    tokens_by_day = fill_daily_data(tokens_map, start, end)
    
    # Daily spend (derived from tokens)
    spend_by_day = [
        DailyDataPoint(date=d.date, value=round((d.value / 1000) * 0.002, 4))
        for d in tokens_by_day
    ]

    # Daily active users
    q_dau = (
        select(
            func.date(Chat.updated_at).label('date'),
            func.count(func.distinct(Chat.user_id)).label('value')
        )
        .where(and_(
            Chat.tenant_id == tenant_id,
            Chat.updated_at >= start,
            Chat.updated_at <= end
        ))
        .group_by(func.date(Chat.updated_at))
        .order_by(func.date(Chat.updated_at))
    )
    dau_result = await db.execute(q_dau)
    dau_map = {r.date.strftime("%Y-%m-%d"): float(r.value) for r in dau_result.all()}
    daily_active_users = fill_daily_data(dau_map, start, end)

    # Messages by role
    q_messages_by_role = (
        select(Message.role, func.count(Message.id))
        .join(Chat)
        .where(and_(
            Chat.tenant_id == tenant_id,
            Message.created_at >= start,
            Message.created_at <= end
        ))
        .group_by(Message.role)
    )
    role_result = await db.execute(q_messages_by_role)
    messages_by_role = {
        str(role.value) if role else "unknown": count
        for role, count in role_result.all()
    }

    # Top users by message count
    q_top_users = (
        select(
            User.id,
            User.email,
            User.full_name,
            func.count(Message.id).label("message_count")
        )
        .join(Chat, Chat.user_id == User.id)
        .join(Message, Message.chat_id == Chat.id)
        .where(and_(
            Chat.tenant_id == tenant_id,
            Message.created_at >= start,
            Message.created_at <= end
        ))
        .group_by(User.id)
        .order_by(desc("message_count"))
        .limit(5)
    )
    top_users_result = await db.execute(q_top_users)
    top_users = [
        TopUserSummary(
            user_id=uid,
            email=email,
            full_name=full_name,
            count=message_count or 0
        )
        for uid, email, full_name, message_count in top_users_result.all()
    ]

    # Model usage breakdown
    model_name_expr = func.coalesce(Chat.model_name, "unknown")
    q_model_usage = (
        select(
            model_name_expr.label("model_name"),
            func.count(Message.id).label("message_count"),
            func.coalesce(func.sum(Message.token_count), 0).label("token_count")
        )
        .join(Message, Message.chat_id == Chat.id)
        .where(and_(
            Chat.tenant_id == tenant_id,
            Message.created_at >= start,
            Message.created_at <= end
        ))
        .group_by(model_name_expr)
        .order_by(desc("message_count"))
        .limit(10)
    )
    model_usage_result = await db.execute(q_model_usage)
    top_models = [
        ModelUsageSummary(
            model_name=model_name,
            message_count=message_count or 0,
            token_count=token_count or 0
        )
        for model_name, message_count, token_count in model_usage_result.all()
    ]
    
    return OverviewStats(
        total_users=total_users,
        active_users=active_users,
        total_chats=total_chats,
        total_messages=total_messages,
        total_tokens=total_tokens,
        estimated_spend_usd=round(estimated_spend, 2),
        new_users=new_users,
        avg_messages_per_chat=avg_messages_per_chat,
        agent_runs=agent_runs,
        agent_runs_failed=agent_runs_failed,
        pipeline_jobs=pipeline_jobs,
        pipeline_jobs_failed=pipeline_jobs_failed,
        tokens_by_day=tokens_by_day,
        spend_by_day=spend_by_day,
        daily_active_users=daily_active_users,
        messages_by_role=messages_by_role,
        top_users=top_users,
        top_models=top_models
    )


async def get_rag_stats(
    db: AsyncSession,
    tenant_id: UUID,
    start: datetime,
    end: datetime
) -> RAGStats:
    """Get RAG statistics."""
    
    # Knowledge stores
    q_stores = (
        select(KnowledgeStore)
        .where(KnowledgeStore.tenant_id == tenant_id)
        .order_by(KnowledgeStore.created_at.desc())
    )
    stores_result = await db.execute(q_stores)
    stores = stores_result.scalars().all()
    
    knowledge_stores = [
        KnowledgeStoreSummary(
            id=s.id,
            name=s.name,
            status=s.status.value if s.status else "unknown",
            document_count=s.document_count or 0,
            chunk_count=s.chunk_count or 0,
            storage_backend=s.backend.value if s.backend else "unknown",
            last_synced_at=s.updated_at  # Use updated_at as proxy for last sync
        )
        for s in stores
    ]

    # Stores by status
    q_store_status = (
        select(KnowledgeStore.status, func.count(KnowledgeStore.id))
        .where(KnowledgeStore.tenant_id == tenant_id)
        .group_by(KnowledgeStore.status)
    )
    store_status_result = await db.execute(q_store_status)
    stores_by_status = {
        str(status.value) if status else "unknown": count
        for status, count in store_status_result.all()
    }
    
    # Total chunks across all stores
    total_chunks = sum(s.chunk_count for s in knowledge_stores)

    # Pipelines by type
    q_pipeline_types = (
        select(VisualPipeline.pipeline_type, func.count(VisualPipeline.id))
        .where(VisualPipeline.tenant_id == tenant_id)
        .group_by(VisualPipeline.pipeline_type)
    )
    pipeline_type_result = await db.execute(q_pipeline_types)
    pipelines_by_type = {
        str(ptype.value) if ptype else "unknown": count
        for ptype, count in pipeline_type_result.all()
    }
    
    q_pipelines_summary = (
        select(
            VisualPipeline.id,
            VisualPipeline.name,
            VisualPipeline.pipeline_type,
            VisualPipeline.is_published,
            func.count(PipelineJob.id).label('job_count'),
            func.max(PipelineJob.created_at).label('last_run_at')
        )
        .outerjoin(ExecutablePipeline, VisualPipeline.id == ExecutablePipeline.visual_pipeline_id)
        .outerjoin(PipelineJob, ExecutablePipeline.id == PipelineJob.executable_pipeline_id)
        .where(VisualPipeline.tenant_id == tenant_id)
        .group_by(VisualPipeline.id, VisualPipeline.name, VisualPipeline.pipeline_type, VisualPipeline.is_published, VisualPipeline.updated_at)
        .order_by(VisualPipeline.updated_at.desc())
    )
    pipelines_result = await db.execute(q_pipelines_summary)
    
    pipelines = []
    for pid, name, ptype, is_published, job_count, last_run in pipelines_result.all():
        pipelines.append(PipelineSummary(
            id=pid,
            name=name,
            pipeline_type=ptype.value if ptype else "unknown",
            is_active=is_published,
            last_run_at=last_run,
            run_count=job_count or 0
        ))
    
    # Recent jobs
    q_recent_jobs = (
        select(PipelineJob, VisualPipeline.name)
        .join(ExecutablePipeline, PipelineJob.executable_pipeline_id == ExecutablePipeline.id)
        .join(VisualPipeline, ExecutablePipeline.visual_pipeline_id == VisualPipeline.id)
        .where(PipelineJob.tenant_id == tenant_id)
        .order_by(PipelineJob.created_at.desc())
        .limit(10)
    )
    recent_jobs_result = await db.execute(q_recent_jobs)
    recent_jobs = [
        JobSummary(
            id=job.id,
            pipeline_name=pipeline_name,
            status=job.status.value if job.status else "unknown",
            started_at=job.started_at,
            completed_at=job.completed_at,
            chunk_count=0  # PipelineJob doesn't track processed items yet
        )
        for job, pipeline_name in recent_jobs_result.all()
    ]

    # Recent failed jobs
    q_recent_failed = (
        select(PipelineJob, VisualPipeline.name)
        .join(ExecutablePipeline, PipelineJob.executable_pipeline_id == ExecutablePipeline.id)
        .join(VisualPipeline, ExecutablePipeline.visual_pipeline_id == VisualPipeline.id)
        .where(and_(
            PipelineJob.tenant_id == tenant_id,
            PipelineJob.status == PipelineJobStatus.FAILED,
            PipelineJob.created_at >= start,
            PipelineJob.created_at <= end
        ))
        .order_by(PipelineJob.created_at.desc())
        .limit(10)
    )
    recent_failed_result = await db.execute(q_recent_failed)
    recent_failed_jobs = [
        JobFailureSummary(
            id=job.id,
            pipeline_name=pipeline_name,
            status=job.status.value if job.status else "unknown",
            error_message=job.error_message,
            created_at=job.created_at
        )
        for job, pipeline_name in recent_failed_result.all()
    ]
    
    # Jobs by day
    q_daily_jobs = (
        select(
            func.date(PipelineJob.created_at).label('date'),
            func.count(PipelineJob.id).label('value')
        )
        .where(and_(
            PipelineJob.tenant_id == tenant_id,
            PipelineJob.created_at >= start,
            PipelineJob.created_at <= end
        ))
        .group_by(func.date(PipelineJob.created_at))
        .order_by(func.date(PipelineJob.created_at))
    )
    daily_jobs_result = await db.execute(q_daily_jobs)
    jobs_map = {r.date.strftime("%Y-%m-%d"): float(r.value) for r in daily_jobs_result.all()}
    jobs_by_day = fill_daily_data(jobs_map, start, end)
    
    # Jobs by status
    q_status = (
        select(PipelineJob.status, func.count(PipelineJob.id))
        .where(and_(
            PipelineJob.tenant_id == tenant_id,
            PipelineJob.created_at >= start,
            PipelineJob.created_at <= end
        ))
        .group_by(PipelineJob.status)
    )
    status_result = await db.execute(q_status)
    jobs_by_status = {
        str(status.value) if status else "unknown": count 
        for status, count in status_result.all()
    }

    # Job duration stats
    duration_expr = (
        func.extract('epoch', PipelineJob.completed_at) -
        func.extract('epoch', PipelineJob.started_at)
    ) * 1000
    q_duration = (
        select(
            func.avg(duration_expr),
            func.percentile_cont(0.95).within_group(duration_expr)
        )
        .where(and_(
            PipelineJob.tenant_id == tenant_id,
            PipelineJob.created_at >= start,
            PipelineJob.created_at <= end,
            PipelineJob.started_at.is_not(None),
            PipelineJob.completed_at.is_not(None)
        ))
    )
    duration_result = await db.execute(q_duration)
    avg_job_duration_ms, p95_job_duration_ms = duration_result.one_or_none() or (None, None)
    if avg_job_duration_ms is not None:
        avg_job_duration_ms = float(avg_job_duration_ms)
    if p95_job_duration_ms is not None:
        p95_job_duration_ms = float(p95_job_duration_ms)

    # Top pipelines by runs and failure rate
    q_top_pipelines = (
        select(
            VisualPipeline.id,
            VisualPipeline.name,
            func.count(PipelineJob.id).label("run_count"),
            func.sum(case((PipelineJob.status == PipelineJobStatus.FAILED, 1), else_=0)).label("failed_count"),
            func.max(PipelineJob.created_at).label("last_run_at")
        )
        .join(ExecutablePipeline, VisualPipeline.id == ExecutablePipeline.visual_pipeline_id)
        .join(PipelineJob, ExecutablePipeline.id == PipelineJob.executable_pipeline_id)
        .where(and_(
            VisualPipeline.tenant_id == tenant_id,
            PipelineJob.created_at >= start,
            PipelineJob.created_at <= end
        ))
        .group_by(VisualPipeline.id, VisualPipeline.name)
        .order_by(desc("run_count"))
        .limit(5)
    )
    top_pipelines_result = await db.execute(q_top_pipelines)
    top_pipelines = []
    for pid, name, run_count, failed_count, last_run_at in top_pipelines_result.all():
        run_count = run_count or 0
        failed_count = failed_count or 0
        failure_rate = round((failed_count / run_count * 100), 2) if run_count > 0 else 0.0
        top_pipelines.append(PipelineUsageSummary(
            id=pid,
            name=name,
            run_count=run_count,
            failed_count=failed_count,
            failure_rate=failure_rate,
            last_run_at=last_run_at
        ))
    
    return RAGStats(
        knowledge_store_count=len(knowledge_stores),
        pipeline_count=len(pipelines),
        total_chunks=total_chunks,
        stores_by_status=stores_by_status,
        pipelines_by_type=pipelines_by_type,
        avg_job_duration_ms=avg_job_duration_ms,
        p95_job_duration_ms=p95_job_duration_ms,
        knowledge_stores=knowledge_stores,
        pipelines=pipelines,
        recent_jobs=recent_jobs,
        top_pipelines=top_pipelines,
        recent_failed_jobs=recent_failed_jobs,
        jobs_by_day=jobs_by_day,
        jobs_by_status=jobs_by_status
    )


async def get_agent_stats(
    db: AsyncSession,
    tenant_id: UUID,
    start: datetime,
    end: datetime
) -> AgentStats:
    """Get agent statistics."""
    
    # Agents with run counts
    q_agents = (
        select(
            Agent,
            func.count(AgentRun.id).label('run_count'),
            func.sum(case((AgentRun.status == RunStatus.failed, 1), else_=0)).label('failed_count'),
            func.max(AgentRun.created_at).label('last_run_at'),
            func.avg(
                func.extract('epoch', AgentRun.completed_at) - func.extract('epoch', AgentRun.started_at)
            ).label('avg_duration_sec')
        )
        .outerjoin(AgentRun, and_(
            AgentRun.agent_id == Agent.id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
        .where(Agent.tenant_id == tenant_id)
        .group_by(Agent.id)
        .order_by(desc('run_count'))
    )
    agents_result = await db.execute(q_agents)
    
    agents = []
    for agent, run_count, failed_count, last_run_at, avg_duration_sec in agents_result.all():
        agents.append(AgentSummary(
            id=agent.id,
            name=agent.name,
            slug=agent.slug,
            status=agent.status.value if agent.status else "unknown",
            run_count=run_count or 0,
            failed_count=failed_count or 0,
            last_run_at=last_run_at,
            avg_duration_ms=(avg_duration_sec * 1000) if avg_duration_sec else None
        ))
    
    # Top agents (already sorted by run_count)
    top_agents = agents[:5]
    
    # Total runs
    total_runs = sum(a.run_count for a in agents)
    total_failed = sum(a.failed_count for a in agents)
    failure_rate = (total_failed / total_runs * 100) if total_runs > 0 else 0
    
    # Runs by day
    q_daily_runs = (
        select(
            func.date(AgentRun.created_at).label('date'),
            func.count(AgentRun.id).label('value')
        )
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
        .group_by(func.date(AgentRun.created_at))
        .order_by(func.date(AgentRun.created_at))
    )
    daily_runs_result = await db.execute(q_daily_runs)
    runs_map = {r.date.strftime("%Y-%m-%d"): float(r.value) for r in daily_runs_result.all()}
    runs_by_day = fill_daily_data(runs_map, start, end)
    
    # Runs by status
    q_status = (
        select(AgentRun.status, func.count(AgentRun.id))
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
        .group_by(AgentRun.status)
    )
    status_result = await db.execute(q_status)
    runs_by_status = {
        str(status.value) if status else "unknown": count 
        for status, count in status_result.all()
    }

    # Duration stats
    duration_expr = (
        func.extract('epoch', AgentRun.completed_at) -
        func.extract('epoch', AgentRun.started_at)
    ) * 1000
    q_duration = (
        select(
            func.avg(duration_expr),
            func.percentile_cont(0.95).within_group(duration_expr)
        )
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end,
            AgentRun.started_at.is_not(None),
            AgentRun.completed_at.is_not(None)
        ))
    )
    duration_result = await db.execute(q_duration)
    avg_run_duration_ms, p95_run_duration_ms = duration_result.one_or_none() or (None, None)
    if avg_run_duration_ms is not None:
        avg_run_duration_ms = float(avg_run_duration_ms)
    if p95_run_duration_ms is not None:
        p95_run_duration_ms = float(p95_run_duration_ms)

    # Average queue time
    queue_expr = (
        func.extract('epoch', AgentRun.started_at) -
        func.extract('epoch', AgentRun.created_at)
    ) * 1000
    q_queue = (
        select(func.avg(queue_expr))
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end,
            AgentRun.started_at.is_not(None)
        ))
    )
    avg_queue_time_ms = (await db.execute(q_queue)).scalar()
    if avg_queue_time_ms is not None:
        avg_queue_time_ms = float(avg_queue_time_ms)

    # Tokens usage
    q_tokens_total = (
        select(func.coalesce(func.sum(AgentRun.usage_tokens), 0))
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
    )
    tokens_used_total = (await db.execute(q_tokens_total)).scalar() or 0

    q_tokens_by_day = (
        select(
            func.date(AgentRun.created_at).label('date'),
            func.coalesce(func.sum(AgentRun.usage_tokens), 0).label('value')
        )
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
        .group_by(func.date(AgentRun.created_at))
        .order_by(func.date(AgentRun.created_at))
    )
    tokens_day_result = await db.execute(q_tokens_by_day)
    tokens_map = {r.date.strftime("%Y-%m-%d"): float(r.value) for r in tokens_day_result.all()}
    tokens_by_day = fill_daily_data(tokens_map, start, end)

    # Top agents by tokens
    q_top_agents_tokens = (
        select(
            Agent.id,
            Agent.name,
            Agent.slug,
            func.count(AgentRun.id).label("run_count"),
            func.coalesce(func.sum(AgentRun.usage_tokens), 0).label("tokens_used")
        )
        .join(AgentRun, AgentRun.agent_id == Agent.id)
        .where(and_(
            Agent.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
        .group_by(Agent.id)
        .order_by(desc("tokens_used"))
        .limit(5)
    )
    top_agents_tokens_result = await db.execute(q_top_agents_tokens)
    top_agents_by_tokens = [
        AgentUsageSummary(
            id=agent_id,
            name=agent_name,
            slug=agent_slug,
            run_count=run_count or 0,
            tokens_used=tokens_used or 0
        )
        for agent_id, agent_name, agent_slug, run_count, tokens_used in top_agents_tokens_result.all()
    ]

    # Top users by runs
    q_top_users_runs = (
        select(
            User.id,
            User.email,
            User.full_name,
            func.count(AgentRun.id).label("run_count")
        )
        .join(AgentRun, AgentRun.user_id == User.id)
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.user_id.is_not(None),
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
        .group_by(User.id)
        .order_by(desc("run_count"))
        .limit(5)
    )
    top_users_runs_result = await db.execute(q_top_users_runs)
    top_users_by_runs = [
        TopUserSummary(
            user_id=user_id,
            email=email,
            full_name=full_name,
            count=run_count or 0
        )
        for user_id, email, full_name, run_count in top_users_runs_result.all()
    ]

    # Recent failures
    q_recent_failures = (
        select(
            AgentRun.id,
            Agent.id,
            Agent.name,
            AgentRun.status,
            User.email,
            AgentRun.error_message,
            AgentRun.created_at
        )
        .join(Agent, AgentRun.agent_id == Agent.id)
        .outerjoin(User, AgentRun.user_id == User.id)
        .where(and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.status == RunStatus.failed,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end
        ))
        .order_by(AgentRun.created_at.desc())
        .limit(10)
    )
    recent_failures_result = await db.execute(q_recent_failures)
    recent_failures = [
        AgentFailureSummary(
            run_id=run_id,
            agent_id=agent_id,
            agent_name=agent_name,
            status=status.value if status else "unknown",
            user_email=user_email,
            error_message=error_message,
            created_at=created_at
        )
        for run_id, agent_id, agent_name, status, user_email, error_message, created_at
        in recent_failures_result.all()
    ]
    
    return AgentStats(
        agent_count=len(agents),
        total_runs=total_runs,
        total_failed=total_failed,
        failure_rate=round(failure_rate, 2),
        avg_run_duration_ms=avg_run_duration_ms,
        p95_run_duration_ms=p95_run_duration_ms,
        avg_queue_time_ms=avg_queue_time_ms,
        tokens_used_total=tokens_used_total,
        agents=agents,
        top_agents=top_agents,
        top_agents_by_tokens=top_agents_by_tokens,
        top_users_by_runs=top_users_by_runs,
        recent_failures=recent_failures,
        runs_by_day=runs_by_day,
        runs_by_status=runs_by_status,
        tokens_by_day=tokens_by_day
    )


async def get_resource_stats(
    db: AsyncSession,
    tenant_id: UUID,
    start: datetime,
    end: datetime
) -> ResourceStats:
    """Get resource statistics."""
    
    # Tools
    q_tools = (
        select(ToolRegistry)
        .where(ToolRegistry.tenant_id == tenant_id)
        .order_by(ToolRegistry.created_at.desc())
    )
    tools_result = await db.execute(q_tools)
    tools = [
        ToolSummary(
            id=t.id,
            name=t.name,
            implementation_type=t.implementation_type.value if t.implementation_type else "unknown",
            status=t.status.value if t.status else "unknown"
        )
        for t in tools_result.scalars().all()
    ]

    q_tools_status = (
        select(ToolRegistry.status, func.count(ToolRegistry.id))
        .where(ToolRegistry.tenant_id == tenant_id)
        .group_by(ToolRegistry.status)
    )
    tools_status_result = await db.execute(q_tools_status)
    tools_by_status = {
        str(status.value) if status else "unknown": count
        for status, count in tools_status_result.all()
    }

    q_tools_type = (
        select(ToolRegistry.implementation_type, func.count(ToolRegistry.id))
        .where(ToolRegistry.tenant_id == tenant_id)
        .group_by(ToolRegistry.implementation_type)
    )
    tools_type_result = await db.execute(q_tools_type)
    tools_by_type = {
        str(impl_type.value) if impl_type else "unknown": count
        for impl_type, count in tools_type_result.all()
    }
    
    # Models (tenant-specific + global)
    q_models = (
        select(
            ModelRegistry,
            func.count(ModelProviderBinding.id).label('provider_count')
        )
        .outerjoin(ModelProviderBinding)
        .where(
            (ModelRegistry.tenant_id == tenant_id) | (ModelRegistry.tenant_id.is_(None))
        )
        .group_by(ModelRegistry.id)
        .order_by(ModelRegistry.created_at.desc())
    )
    models_result = await db.execute(q_models)
    models = [
        ModelSummary(
            id=m.id,
            name=m.name,
            slug=m.slug,
            capability_type=m.capability_type.value if m.capability_type else "unknown",
            status=m.status.value if m.status else "unknown",
            provider_count=provider_count or 0
        )
        for m, provider_count in models_result.all()
    ]

    q_models_capability = (
        select(ModelRegistry.capability_type, func.count(ModelRegistry.id))
        .where(
            (ModelRegistry.tenant_id == tenant_id) | (ModelRegistry.tenant_id.is_(None))
        )
        .group_by(ModelRegistry.capability_type)
    )
    models_capability_result = await db.execute(q_models_capability)
    models_by_capability = {
        str(capability.value) if capability else "unknown": count
        for capability, count in models_capability_result.all()
    }

    q_models_status = (
        select(ModelRegistry.status, func.count(ModelRegistry.id))
        .where(
            (ModelRegistry.tenant_id == tenant_id) | (ModelRegistry.tenant_id.is_(None))
        )
        .group_by(ModelRegistry.status)
    )
    models_status_result = await db.execute(q_models_status)
    models_by_status = {
        str(status.value) if status else "unknown": count
        for status, count in models_status_result.all()
    }

    q_provider_bindings = (
        select(ModelProviderBinding.provider, func.count(ModelProviderBinding.id))
        .where(
            (ModelProviderBinding.tenant_id == tenant_id) | (ModelProviderBinding.tenant_id.is_(None))
        )
        .group_by(ModelProviderBinding.provider)
        .order_by(desc(func.count(ModelProviderBinding.id)))
    )
    provider_bindings_result = await db.execute(q_provider_bindings)
    provider_bindings_by_provider = [
        ProviderUsageSummary(
            provider=str(provider.value) if provider else "unknown",
            count=count
        )
        for provider, count in provider_bindings_result.all()
    ]
    
    # Artifacts (custom operators)
    q_artifacts = (
        select(CustomOperator)
        .where(CustomOperator.tenant_id == tenant_id)
        .order_by(CustomOperator.created_at.desc())
    )
    artifacts_result = await db.execute(q_artifacts)
    artifacts = [
        ArtifactSummary(
            id=a.id,
            name=a.name,
            category=a.category.value if a.category else "unknown",
            version=a.version or "1.0.0",
            is_active=a.is_active
        )
        for a in artifacts_result.scalars().all()
    ]

    q_artifacts_category = (
        select(CustomOperator.category, func.count(CustomOperator.id))
        .where(CustomOperator.tenant_id == tenant_id)
        .group_by(CustomOperator.category)
    )
    artifacts_category_result = await db.execute(q_artifacts_category)
    artifacts_by_category = {
        str(category.value) if category else "unknown": count
        for category, count in artifacts_category_result.all()
    }

    q_artifacts_active = (
        select(CustomOperator.is_active, func.count(CustomOperator.id))
        .where(CustomOperator.tenant_id == tenant_id)
        .group_by(CustomOperator.is_active)
    )
    artifacts_active_result = await db.execute(q_artifacts_active)
    artifacts_by_active = {
        "active" if is_active else "inactive": count
        for is_active, count in artifacts_active_result.all()
    }
    
    return ResourceStats(
        tool_count=len(tools),
        model_count=len(models),
        artifact_count=len(artifacts),
        tools_by_status=tools_by_status,
        tools_by_type=tools_by_type,
        models_by_capability=models_by_capability,
        models_by_status=models_by_status,
        provider_bindings_by_provider=provider_bindings_by_provider,
        artifacts_by_category=artifacts_by_category,
        artifacts_by_active=artifacts_by_active,
        tools=tools,
        models=models,
        artifacts=artifacts
    )


# --- Main Endpoint ---

@router.get("/summary", response_model=StatsResponse)
async def get_stats_summary(
    section: Literal["overview", "rag", "agents", "resources"] = Query(
        default="overview",
        description="Which stats section to retrieve"
    ),
    days: int = Query(
        default=7,
        ge=1,
        le=90,
        description="Number of days for trend data"
    ),
    start_date: Optional[str] = Query(
        default=None,
        description="Optional ISO start date (YYYY-MM-DD or full ISO datetime)"
    ),
    end_date: Optional[str] = Query(
        default=None,
        description="Optional ISO end date (YYYY-MM-DD or full ISO datetime)"
    ),
    context: Dict[str, Any] = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
) -> StatsResponse:
    """
    Get platform statistics for the admin dashboard.
    
    Sections:
    - overview: Cross-platform KPIs (users, chats, tokens, runs)
    - rag: RAG pipelines and knowledge stores
    - agents: Agent inventory and run statistics
    - resources: Tools, models, and artifacts
    """
    tenant_id = context["tenant_id"]
    
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context available")

    period_start, period_end = get_period_range(days, start_date, end_date)
    period_days = max(1, (period_end.date() - period_start.date()).days + 1)
    
    response = StatsResponse(
        section=section,
        period_days=period_days,
        generated_at=datetime.now(timezone.utc),
        period_start=period_start,
        period_end=period_end
    )
    
    if section == "overview":
        response.overview = await get_overview_stats(db, tenant_id, period_start, period_end)
    elif section == "rag":
        response.rag = await get_rag_stats(db, tenant_id, period_start, period_end)
    elif section == "agents":
        response.agents = await get_agent_stats(db, tenant_id, period_start, period_end)
    elif section == "resources":
        response.resources = await get_resource_stats(db, tenant_id, period_start, period_end)
    
    return response
