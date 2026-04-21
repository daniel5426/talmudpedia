import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import load_only
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.identity import OrgMembership
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCustomDomain,
    PublishedAppDraftDevSession,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
)
from .published_apps_admin_shared import _slugify

CODING_AGENT_SURFACE = "published_app_coding_agent"
_ACTIVE_PROJECT_ID: ContextVar[UUID | None] = ContextVar("published_apps_active_project_id", default=None)


def _active_project_id() -> UUID:
    project_id = _ACTIVE_PROJECT_ID.get()
    if project_id is None:
        raise HTTPException(status_code=403, detail="Project context required")
    return project_id


def _publish_job_stale_timeout_seconds() -> int:
    raw = (os.getenv("APPS_PUBLISH_ACTIVE_JOB_STALE_TIMEOUT_SECONDS") or "").strip()
    try:
        return max(60, int(raw or "100"))
    except Exception:
        return 100


async def _expire_stale_publish_job_if_needed(
    db: AsyncSession,
    *,
    job: PublishedAppPublishJob,
) -> bool:
    status_value = job.status.value if hasattr(job.status, "value") else str(job.status)
    if status_value not in {
        PublishedAppPublishJobStatus.queued.value,
        PublishedAppPublishJobStatus.running.value,
    }:
        return False

    timeout_seconds = _publish_job_stale_timeout_seconds()
    reference_at = (
        job.last_heartbeat_at
        or job.started_at
        or job.updated_at
        or job.created_at
    )
    if reference_at is None:
        return False
    if reference_at.tzinfo is None:
        reference_at = reference_at.replace(tzinfo=timezone.utc)

    stale_after = reference_at + timedelta(seconds=timeout_seconds)
    now = datetime.now(timezone.utc)
    if now < stale_after:
        return False

    message = (
        f"Publish job timed out after {timeout_seconds}s without heartbeat "
        f"(last_stage={job.stage or 'unknown'})."
    )
    diagnostics = list(job.diagnostics or [])
    diagnostics.append(
        {
            "kind": "publish_job_timeout",
            "message": message,
            "last_stage": str(job.stage or "unknown"),
            "last_heartbeat_at": reference_at.isoformat(),
            "timeout_seconds": str(timeout_seconds),
        }
    )
    job.status = PublishedAppPublishJobStatus.failed
    job.stage = "timed_out"
    job.error = message
    job.finished_at = now
    job.last_heartbeat_at = now
    job.diagnostics = diagnostics
    await db.flush()
    return True


async def _resolve_organization_admin_context(
    request: Request,
    principal: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    project_raw = principal.get("project_id")
    if not project_raw:
        raise HTTPException(status_code=403, detail="Project context required")
    try:
        active_project_id = UUID(str(project_raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid project context") from exc

    if principal.get("type") == "workload":
        organization_id = principal.get("organization_id")
        if not organization_id:
            raise HTTPException(status_code=403, detail="Organization context required")
        _ACTIVE_PROJECT_ID.set(active_project_id)
        return {
            "organization_id": UUID(str(organization_id)),
            "project_id": active_project_id,
            "user": None,
            "is_system_admin": False,
        }

    user = principal.get("user")
    if user is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    header_tenant = request.headers.get("X-Organization-ID")
    if header_tenant:
        try:
            organization_uuid = UUID(str(header_tenant))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid X-Organization-ID header")
        principal_organization_id = principal.get("organization_id")
        if principal_organization_id and str(principal_organization_id) != str(organization_uuid):
            raise HTTPException(status_code=403, detail="Requested organization does not match active project context")
        membership_result = await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == user.id,
                OrgMembership.organization_id == organization_uuid,
            ).limit(1)
        )
        membership = membership_result.scalar_one_or_none()
        if membership is None and user.role != "admin":
            raise HTTPException(status_code=403, detail="Not a member of the requested organization")
        _ACTIVE_PROJECT_ID.set(active_project_id)
        return {
            "organization_id": organization_uuid,
            "project_id": active_project_id,
            "user": user,
            "is_system_admin": user.role == "admin",
        }

    membership_result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == user.id).limit(1)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is not None:
        _ACTIVE_PROJECT_ID.set(active_project_id)
        return {
            "organization_id": membership.organization_id,
            "project_id": active_project_id,
            "user": user,
            "is_system_admin": user.role == "admin",
        }

    organization_id = principal.get("organization_id")
    if user.role == "admin" and organization_id:
        _ACTIVE_PROJECT_ID.set(active_project_id)
        return {
            "organization_id": UUID(str(organization_id)),
            "project_id": active_project_id,
            "user": user,
            "is_system_admin": True,
        }
    raise HTTPException(status_code=403, detail="Organization context required")


def _assert_can_manage_apps(ctx: Dict[str, Any]) -> None:
    if ctx.get("is_system_admin"):
        return


async def _validate_agent(db: AsyncSession, organization_id: UUID, agent_id: UUID) -> Agent:
    result = await db.execute(
        select(Agent).where(
            and_(
                Agent.id == agent_id,
                Agent.organization_id == organization_id,
                Agent.project_id == _active_project_id(),
            )
        ).limit(1)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _generate_public_id(db: AsyncSession) -> str:
    for _ in range(200):
        candidate = f"app_{uuid.uuid4().hex[:24]}"
        result = await db.execute(select(PublishedApp.id).where(PublishedApp.public_id == candidate).limit(1))
        if result.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(status_code=409, detail="Could not generate a unique app public id")


async def _get_app_for_tenant(db: AsyncSession, organization_id: UUID, app_id: UUID) -> PublishedApp:
    result = await db.execute(
        select(PublishedApp).where(
            and_(
                PublishedApp.id == app_id,
                PublishedApp.organization_id == organization_id,
                PublishedApp.project_id == _active_project_id(),
            )
        ).limit(1)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Published app not found")
    return app


async def _get_revision(db: AsyncSession, revision_id: Optional[UUID]) -> Optional[PublishedAppRevision]:
    if revision_id is None:
        return None
    result = await db.execute(select(PublishedAppRevision).where(PublishedAppRevision.id == revision_id).limit(1))
    return result.scalar_one_or_none()


async def _get_revision_for_app(db: AsyncSession, app_id: UUID, revision_id: UUID) -> PublishedAppRevision:
    result = await db.execute(
        select(PublishedAppRevision).where(
            and_(
                PublishedAppRevision.id == revision_id,
                PublishedAppRevision.published_app_id == app_id,
            )
        ).limit(1)
    )
    revision = result.scalar_one_or_none()
    if revision is None:
        raise HTTPException(status_code=404, detail="Revision not found")
    return revision


async def _get_draft_dev_session_for_scope(
    db: AsyncSession,
    *,
    app_id: UUID,
    user_id: UUID,
) -> Optional[PublishedAppDraftDevSession]:
    result = await db.execute(
        select(PublishedAppDraftDevSession)
        .options(
            load_only(
                PublishedAppDraftDevSession.id,
                PublishedAppDraftDevSession.published_app_id,
                PublishedAppDraftDevSession.user_id,
                PublishedAppDraftDevSession.revision_id,
                PublishedAppDraftDevSession.draft_workspace_id,
                PublishedAppDraftDevSession.status,
                PublishedAppDraftDevSession.sandbox_id,
                PublishedAppDraftDevSession.runtime_generation,
                PublishedAppDraftDevSession.runtime_backend,
                PublishedAppDraftDevSession.backend_metadata,
                PublishedAppDraftDevSession.preview_url,
                PublishedAppDraftDevSession.idle_timeout_seconds,
                PublishedAppDraftDevSession.expires_at,
                PublishedAppDraftDevSession.last_activity_at,
                PublishedAppDraftDevSession.dependency_hash,
                PublishedAppDraftDevSession.last_error,
                PublishedAppDraftDevSession.created_at,
                PublishedAppDraftDevSession.updated_at,
            )
        )
        .where(
            and_(
                PublishedAppDraftDevSession.published_app_id == app_id,
                PublishedAppDraftDevSession.user_id == user_id,
            )
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _count_active_coding_runs_for_scope(
    db: AsyncSession,
    *,
    app_id: UUID,
    user_id: UUID | None,
) -> int:
    _ = user_id
    result = await db.execute(
        select(func.count(AgentRun.id)).where(
            and_(
                AgentRun.surface == CODING_AGENT_SURFACE,
                AgentRun.published_app_id == app_id,
                AgentRun.status.in_([RunStatus.queued, RunStatus.running]),
            )
        )
    )
    return int(result.scalar() or 0)


async def _get_publish_job_for_app(
    db: AsyncSession,
    *,
    app_id: UUID,
    job_id: UUID,
) -> PublishedAppPublishJob:
    result = await db.execute(
        select(PublishedAppPublishJob).where(
            and_(
                PublishedAppPublishJob.id == job_id,
                PublishedAppPublishJob.published_app_id == app_id,
            )
        ).limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Publish job not found")
    return job


async def _get_active_publish_job_for_app(
    db: AsyncSession,
    *,
    app_id: UUID,
) -> Optional[PublishedAppPublishJob]:
    result = await db.execute(
        select(PublishedAppPublishJob)
        .where(
            and_(
                PublishedAppPublishJob.published_app_id == app_id,
                PublishedAppPublishJob.status.in_(
                    [
                        PublishedAppPublishJobStatus.queued,
                        PublishedAppPublishJobStatus.running,
                    ]
                ),
            )
        )
        .order_by(PublishedAppPublishJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None
    expired = await _expire_stale_publish_job_if_needed(db, job=job)
    if expired:
        return None
    return job


async def _get_custom_domain_for_app(
    db: AsyncSession,
    *,
    app_id: UUID,
    domain_id: UUID,
) -> PublishedAppCustomDomain:
    result = await db.execute(
        select(PublishedAppCustomDomain).where(
            and_(
                PublishedAppCustomDomain.id == domain_id,
                PublishedAppCustomDomain.published_app_id == app_id,
            )
        ).limit(1)
    )
    domain = result.scalar_one_or_none()
    if domain is None:
        raise HTTPException(status_code=404, detail="Custom domain not found")
    return domain


async def _ensure_current_draft_revision(db: AsyncSession, app: PublishedApp, actor_id: Optional[UUID]) -> PublishedAppRevision:
    _ = actor_id
    draft = await _get_revision(db, app.current_draft_revision_id)
    if draft is not None:
        return draft
    raise HTTPException(
        status_code=409,
        detail={
            "code": "DRAFT_REVISION_MISSING",
            "message": "Current draft revision is missing. Reopen or recreate the app workspace.",
            "app_id": str(app.id),
        },
    )
