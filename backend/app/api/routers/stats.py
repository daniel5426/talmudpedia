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
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadTurn
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus, AgentStatus
from app.db.postgres.models.rag import (
    KnowledgeStore, RAGPipeline, VisualPipeline, ExecutablePipeline, 
    PipelineJob, PipelineJobStatus, PipelineType
)
from app.db.postgres.models.registry import (
    ToolRegistry, ModelRegistry, ModelProviderBinding, ToolStatus
)
from app.db.postgres.models.operators import CustomOperator
from app.services.admin_monitoring_service import AdminMonitoringService

from app.api.schemas.stats import (
    StatsResponse, OverviewStats, RAGStats, AgentStats, ResourceStats,
    DailyDataPoint, KnowledgeStoreSummary, PipelineSummary, JobSummary,
    AgentSummary, ToolSummary, ModelSummary, ArtifactSummary, RecentThreadSummary,
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


def normalize_grouped_date(value: Any) -> str:
    """Normalize DB grouped date values across engines."""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value).split("T")[0]


def normalize_grouped_enum(value: Any) -> str:
    """Normalize DB grouped enum values across engines."""
    if value is None:
        return "unknown"
    return str(getattr(value, "value", value))


def supports_percentile_cont(db: AsyncSession) -> bool:
    bind = db.get_bind()
    return bool(bind and bind.dialect.name != "sqlite")


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
    data_map = {normalize_grouped_date(r.date): float(r.value) for r in result.all()}
    return fill_daily_data(data_map, start, end)


# --- Section Handlers ---

async def get_overview_stats(
    db: AsyncSession,
    tenant_id: UUID,
    start: datetime,
    end: datetime
) -> OverviewStats:
    """Get overview statistics."""
    monitoring = AdminMonitoringService(db=db, tenant_id=tenant_id)
    actor_aggregates = await monitoring._build_actor_aggregates(month_start=start, month_end=end)
    total_users = len(actor_aggregates)
    active_users = await monitoring.active_actor_count(start=start, end=end)
    total_chats = await monitoring.count_threads(start=start, end=end)

    q_messages = (
        select(func.count(AgentThreadTurn.id))
        .join(AgentThread, AgentThreadTurn.thread_id == AgentThread.id)
        .where(
            and_(
                AgentThread.tenant_id == tenant_id,
                AgentThreadTurn.created_at >= start,
                AgentThreadTurn.created_at <= end,
            )
        )
    )
    total_messages = int((await db.execute(q_messages)).scalar() or 0)

    q_tokens = select(func.coalesce(func.sum(AgentRun.usage_tokens), 0)).where(
        and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end,
        )
    )
    total_tokens = int((await db.execute(q_tokens)).scalar() or 0)

    q_runs = select(func.count(AgentRun.id)).where(
        and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end,
        )
    )
    agent_runs = int((await db.execute(q_runs)).scalar() or 0)

    q_failed_runs = select(func.count(AgentRun.id)).where(
        and_(
            AgentRun.tenant_id == tenant_id,
            AgentRun.status == RunStatus.failed,
            AgentRun.created_at >= start,
            AgentRun.created_at <= end,
        )
    )
    agent_runs_failed = int((await db.execute(q_failed_runs)).scalar() or 0)

    q_jobs = select(func.count(PipelineJob.id)).where(
        and_(
            PipelineJob.tenant_id == tenant_id,
            PipelineJob.created_at >= start,
            PipelineJob.created_at <= end,
        )
    )
    pipeline_jobs = int((await db.execute(q_jobs)).scalar() or 0)

    q_failed_jobs = select(func.count(PipelineJob.id)).where(
        and_(
            PipelineJob.tenant_id == tenant_id,
            PipelineJob.status == PipelineJobStatus.FAILED,
            PipelineJob.created_at >= start,
            PipelineJob.created_at <= end,
        )
    )
    pipeline_jobs_failed = int((await db.execute(q_failed_jobs)).scalar() or 0)

    new_users = sum(
        1
        for actor in actor_aggregates.values()
        if actor.created_at is not None and actor.created_at >= start and actor.created_at <= end
    )

    avg_messages_per_chat = round(total_messages / total_chats, 2) if total_chats > 0 else 0.0
    estimated_spend = (total_tokens / 1000) * 0.002

    q_daily_tokens = (
        select(
            func.date(AgentRun.created_at).label("date"),
            func.coalesce(func.sum(AgentRun.usage_tokens), 0).label("value"),
        )
        .where(
            and_(
                AgentRun.tenant_id == tenant_id,
                AgentRun.created_at >= start,
                AgentRun.created_at <= end,
            )
        )
        .group_by(func.date(AgentRun.created_at))
        .order_by(func.date(AgentRun.created_at))
    )
    tokens_result = await db.execute(q_daily_tokens)
    tokens_map = {normalize_grouped_date(r.date): float(r.value) for r in tokens_result.all()}
    tokens_by_day = fill_daily_data(tokens_map, start, end)
    spend_by_day = [
        DailyDataPoint(date=d.date, value=round((d.value / 1000) * 0.002, 4))
        for d in tokens_by_day
    ]

    daily_active_rows = await monitoring.daily_active_actor_counts(start=start, end=end)
    dau_map = {str(item["date"]): float(item["count"]) for item in daily_active_rows}
    daily_active_users = fill_daily_data(dau_map, start, end)

    q_user_turns = (
        select(func.count(AgentThreadTurn.id))
        .join(AgentThread, AgentThreadTurn.thread_id == AgentThread.id)
        .where(
            and_(
                AgentThread.tenant_id == tenant_id,
                AgentThreadTurn.created_at >= start,
                AgentThreadTurn.created_at <= end,
                AgentThreadTurn.user_input_text.is_not(None),
            )
        )
    )
    q_assistant_turns = (
        select(func.count(AgentThreadTurn.id))
        .join(AgentThread, AgentThreadTurn.thread_id == AgentThread.id)
        .where(
            and_(
                AgentThread.tenant_id == tenant_id,
                AgentThreadTurn.created_at >= start,
                AgentThreadTurn.created_at <= end,
                AgentThreadTurn.assistant_output_text.is_not(None),
            )
        )
    )
    messages_by_role = {
        "user": int((await db.execute(q_user_turns)).scalar() or 0),
        "assistant": int((await db.execute(q_assistant_turns)).scalar() or 0),
    }

    top_users_rows = await monitoring.top_actor_summaries_by_runs(start=start, end=end, limit=5)
    top_users = [
        TopUserSummary(
            user_id=str(item["user_id"]),
            display_name=item["display_name"],
            email=item.get("email"),
            actor_type=item.get("actor_type"),
            full_name=item["display_name"],
            count=int(item["count"] or 0),
        )
        for item in top_users_rows
    ]

    model_name_expr = func.coalesce(ModelRegistry.name, "unknown")
    q_model_usage = (
        select(
            model_name_expr.label("model_name"),
            func.count(AgentRun.id).label("message_count"),
            func.coalesce(func.sum(AgentRun.usage_tokens), 0).label("token_count"),
        )
        .outerjoin(ModelRegistry, AgentRun.resolved_model_id == ModelRegistry.id)
        .where(
            and_(
                AgentRun.tenant_id == tenant_id,
                AgentRun.created_at >= start,
                AgentRun.created_at <= end,
            )
        )
        .group_by(model_name_expr)
        .order_by(desc("message_count"))
        .limit(10)
    )
    model_usage_result = await db.execute(q_model_usage)
    top_models = [
        ModelUsageSummary(
            model_name=model_name,
            message_count=int(message_count or 0),
            token_count=int(token_count or 0),
        )
        for model_name, message_count, token_count in model_usage_result.all()
    ]

    recent_threads_rows = await monitoring.latest_thread_summaries(
        month_start=start,
        month_end=end,
        limit=5,
    )
    recent_threads = [
        RecentThreadSummary(
            id=UUID(str(item["id"])),
            title=item.get("title"),
            created_at=item.get("created_at"),
            actor_display=item.get("user_email") or "Unknown actor",
            actor_email=item.get("user_email"),
        )
        for item in recent_threads_rows
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
        top_models=top_models,
        recent_threads=recent_threads,
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
        normalize_grouped_enum(status): count
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
        normalize_grouped_enum(ptype): count
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
    jobs_map = {normalize_grouped_date(r.date): float(r.value) for r in daily_jobs_result.all()}
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
        normalize_grouped_enum(status): count
        for status, count in status_result.all()
    }

    # Job duration stats
    duration_expr = (
        func.extract('epoch', PipelineJob.completed_at) -
        func.extract('epoch', PipelineJob.started_at)
    ) * 1000
    if supports_percentile_cont(db):
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
    else:
        q_duration = (
            select(func.avg(duration_expr))
            .where(and_(
                PipelineJob.tenant_id == tenant_id,
                PipelineJob.created_at >= start,
                PipelineJob.created_at <= end,
                PipelineJob.started_at.is_not(None),
                PipelineJob.completed_at.is_not(None)
            ))
        )
        avg_job_duration_ms = (await db.execute(q_duration)).scalar()
        p95_job_duration_ms = None
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
    end: datetime,
    agent_id: UUID | None = None,
) -> AgentStats:
    """Get agent statistics."""
    monitoring = AdminMonitoringService(db=db, tenant_id=tenant_id)
    thread_contexts = await monitoring._load_thread_contexts(
        month_start=start,
        month_end=end,
        agent_id=agent_id,
        app_id=None,
    )
    context_by_thread_id = {str(context.thread.id): context for context in thread_contexts}

    q_agents = (
        select(
            Agent,
            func.count(func.distinct(AgentRun.thread_id)).label("thread_count"),
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
    if agent_id:
        q_agents = q_agents.where(Agent.id == agent_id)
    agents_result = await db.execute(q_agents)

    q_daily_threads = (
        select(
            AgentThread.agent_id.label("agent_id"),
            func.date(AgentThread.created_at).label("date"),
            func.count(AgentThread.id).label("value"),
        )
        .where(and_(
            AgentThread.tenant_id == tenant_id,
            AgentThread.created_at >= start,
            AgentThread.created_at <= end,
            AgentThread.agent_id.is_not(None),
        ))
        .group_by(AgentThread.agent_id, func.date(AgentThread.created_at))
        .order_by(AgentThread.agent_id, func.date(AgentThread.created_at))
    )
    if agent_id:
        q_daily_threads = q_daily_threads.where(AgentThread.agent_id == agent_id)
    daily_threads_result = await db.execute(q_daily_threads)
    thread_maps_by_agent: dict[str, dict[str, float]] = {}
    for row in daily_threads_result.all():
        agent_key = str(row.agent_id)
        thread_maps_by_agent.setdefault(agent_key, {})[normalize_grouped_date(row.date)] = float(row.value)
    
    agents = []
    for agent, thread_count, run_count, failed_count, last_run_at, avg_duration_sec in agents_result.all():
        agents.append(AgentSummary(
            id=agent.id,
            name=agent.name,
            slug=agent.slug,
            status=agent.status.value if agent.status else "unknown",
            thread_count=int(thread_count or 0),
            threads_by_day=fill_daily_data(thread_maps_by_agent.get(str(agent.id), {}), start, end),
            run_count=run_count or 0,
            failed_count=failed_count or 0,
            last_run_at=last_run_at,
            avg_duration_ms=(avg_duration_sec * 1000) if avg_duration_sec else None
        ))
    
    top_agents = agents[:5]
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
    if agent_id:
        q_daily_runs = q_daily_runs.where(AgentRun.agent_id == agent_id)
    daily_runs_result = await db.execute(q_daily_runs)
    runs_map = {normalize_grouped_date(r.date): float(r.value) for r in daily_runs_result.all()}
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
    if agent_id:
        q_status = q_status.where(AgentRun.agent_id == agent_id)
    status_result = await db.execute(q_status)
    runs_by_status = {
        normalize_grouped_enum(status): count
        for status, count in status_result.all()
    }

    # Duration stats
    duration_expr = (
        func.extract('epoch', AgentRun.completed_at) -
        func.extract('epoch', AgentRun.started_at)
    ) * 1000
    if supports_percentile_cont(db):
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
        if agent_id:
            q_duration = q_duration.where(AgentRun.agent_id == agent_id)
        duration_result = await db.execute(q_duration)
        avg_run_duration_ms, p95_run_duration_ms = duration_result.one_or_none() or (None, None)
    else:
        q_duration = (
            select(func.avg(duration_expr))
            .where(and_(
                AgentRun.tenant_id == tenant_id,
                AgentRun.created_at >= start,
                AgentRun.created_at <= end,
                AgentRun.started_at.is_not(None),
                AgentRun.completed_at.is_not(None)
            ))
        )
        if agent_id:
            q_duration = q_duration.where(AgentRun.agent_id == agent_id)
        avg_run_duration_ms = (await db.execute(q_duration)).scalar()
        p95_run_duration_ms = None
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
    if agent_id:
        q_queue = q_queue.where(AgentRun.agent_id == agent_id)
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
    if agent_id:
        q_tokens_total = q_tokens_total.where(AgentRun.agent_id == agent_id)
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
    if agent_id:
        q_tokens_by_day = q_tokens_by_day.where(AgentRun.agent_id == agent_id)
    tokens_day_result = await db.execute(q_tokens_by_day)
    tokens_map = {normalize_grouped_date(r.date): float(r.value) for r in tokens_day_result.all()}
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
    if agent_id:
        q_top_agents_tokens = q_top_agents_tokens.where(Agent.id == agent_id)
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

    top_users_by_runs = [
        TopUserSummary(
            user_id=str(item["user_id"]),
            display_name=item["display_name"],
            email=item.get("email"),
            actor_type=item.get("actor_type"),
            full_name=item["display_name"],
            count=int(item["count"] or 0),
        )
        for item in await monitoring.top_actor_summaries_by_runs(
            start=start,
            end=end,
            agent_id=agent_id,
            limit=5,
        )
    ]

    q_recent_failures = (
        select(
            AgentRun.id,
            Agent.id,
            Agent.name,
            AgentRun.status,
            AgentRun.thread_id,
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
    if agent_id:
        q_recent_failures = q_recent_failures.where(AgentRun.agent_id == agent_id)
    recent_failures_result = await db.execute(q_recent_failures)
    recent_failures = [
        AgentFailureSummary(
            run_id=run_id,
            agent_id=agent_id,
            agent_name=agent_name,
            status=normalize_grouped_enum(status),
            user_email=user_email or (
                context_by_thread_id.get(str(thread_id)).actor_email
                if thread_id is not None and context_by_thread_id.get(str(thread_id)) is not None
                else (
                    context_by_thread_id.get(str(thread_id)).actor_display
                    if thread_id is not None and context_by_thread_id.get(str(thread_id)) is not None
                    else None
                )
            ),
            error_message=error_message,
            created_at=created_at
        )
        for run_id, agent_id, agent_name, status, thread_id, user_email, error_message, created_at
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
        normalize_grouped_enum(status): count
        for status, count in tools_status_result.all()
    }

    q_tools_type = (
        select(ToolRegistry.implementation_type, func.count(ToolRegistry.id))
        .where(ToolRegistry.tenant_id == tenant_id)
        .group_by(ToolRegistry.implementation_type)
    )
    tools_type_result = await db.execute(q_tools_type)
    tools_by_type = {
        normalize_grouped_enum(impl_type): count
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
        normalize_grouped_enum(capability): count
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
        normalize_grouped_enum(status): count
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
            provider=normalize_grouped_enum(provider),
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
    agent_id: Optional[UUID] = Query(
        default=None,
        description="Optional agent scope for the agents section"
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
        response.agents = await get_agent_stats(db, tenant_id, period_start, period_end, agent_id=agent_id)
    elif section == "resources":
        response.resources = await get_resource_stats(db, tenant_id, period_start, period_end)
    
    return response
