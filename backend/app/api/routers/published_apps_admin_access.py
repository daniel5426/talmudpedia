import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import load_only
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import OrgMembership, OrgRole
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCustomDomain,
    PublishedAppDraftDevSession,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_templates import build_template_files, get_template
from app.services.published_app_versioning import create_app_version

from .published_apps_admin_builder_core import _next_build_seq
from .published_apps_admin_shared import APP_SLUG_PATTERN, _slugify

CODING_AGENT_SURFACE = "published_app_coding_agent"


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


async def _resolve_tenant_admin_context(
    request: Request,
    principal: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    if principal.get("type") == "workload":
        tenant_id = principal.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        return {
            "tenant_id": UUID(str(tenant_id)),
            "user": None,
            "is_system_admin": False,
            "org_role": None,
        }

    user = principal.get("user")
    if user is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    header_tenant = request.headers.get("X-Tenant-ID")
    if header_tenant:
        try:
            tenant_uuid = UUID(str(header_tenant))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid X-Tenant-ID header")
        membership_result = await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == user.id,
                OrgMembership.tenant_id == tenant_uuid,
            ).limit(1)
        )
        membership = membership_result.scalar_one_or_none()
        if membership is None and user.role != "admin":
            raise HTTPException(status_code=403, detail="Not a member of the requested tenant")
        org_role = (
            str(getattr(membership.role, "value", membership.role))
            if membership
            else OrgRole.owner.value
        )
        return {
            "tenant_id": tenant_uuid,
            "user": user,
            "is_system_admin": user.role == "admin",
            "org_role": org_role,
        }

    membership_result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == user.id).limit(1)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is not None:
        return {
            "tenant_id": membership.tenant_id,
            "user": user,
            "is_system_admin": user.role == "admin",
            "org_role": str(getattr(membership.role, "value", membership.role)),
        }

    tenant_id = principal.get("tenant_id")
    if user.role == "admin" and tenant_id:
        return {
            "tenant_id": UUID(str(tenant_id)),
            "user": user,
            "is_system_admin": True,
            "org_role": OrgRole.owner.value,
        }
    raise HTTPException(status_code=403, detail="Tenant context required")


def _assert_can_manage_apps(ctx: Dict[str, Any]) -> None:
    if ctx.get("is_system_admin"):
        return
    role = str(ctx.get("org_role") or "")
    if role not in {OrgRole.owner.value, OrgRole.admin.value}:
        raise HTTPException(status_code=403, detail="Insufficient permissions for apps management")


async def _validate_agent(db: AsyncSession, tenant_id: UUID, agent_id: UUID) -> Agent:
    result = await db.execute(
        select(Agent).where(and_(Agent.id == agent_id, Agent.tenant_id == tenant_id)).limit(1)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status != AgentStatus.published:
        raise HTTPException(status_code=400, detail="Only published agents can be attached to apps")
    return agent


async def _generate_unique_slug(db: AsyncSession, base: str) -> str:
    candidate = _slugify(base)
    if APP_SLUG_PATTERN.match(candidate):
        result = await db.execute(select(PublishedApp.id).where(PublishedApp.slug == candidate).limit(1))
        if result.scalar_one_or_none() is None:
            return candidate

    for idx in range(2, 200):
        next_candidate = f"{candidate[:58]}-{idx}"
        result = await db.execute(select(PublishedApp.id).where(PublishedApp.slug == next_candidate).limit(1))
        if result.scalar_one_or_none() is None:
            return next_candidate

    raise HTTPException(status_code=409, detail="Could not generate a unique app slug")


async def _get_app_for_tenant(db: AsyncSession, tenant_id: UUID, app_id: UUID) -> PublishedApp:
    result = await db.execute(
        select(PublishedApp).where(
            and_(PublishedApp.id == app_id, PublishedApp.tenant_id == tenant_id)
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
                PublishedAppDraftDevSession.status,
                PublishedAppDraftDevSession.sandbox_id,
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
    if user_id is None:
        return 0
    result = await db.execute(
        select(func.count(AgentRun.id)).where(
            and_(
                AgentRun.surface == CODING_AGENT_SURFACE,
                AgentRun.published_app_id == app_id,
                or_(
                    AgentRun.initiator_user_id == user_id,
                    and_(
                        AgentRun.initiator_user_id.is_(None),
                        AgentRun.user_id == user_id,
                    ),
                ),
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
    draft = await _get_revision(db, app.current_draft_revision_id)
    if draft is not None:
        return draft

    files = build_template_files(
        app.template_key or "chat-classic",
        runtime_context={
            "app_id": str(app.id),
            "app_slug": app.slug,
            "agent_id": str(app.agent_id),
        },
    )
    created = await create_app_version(
        db,
        app=app,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key or "chat-classic",
        entry_file=get_template(app.template_key or "chat-classic").entry_file,
        files=files,
        created_by=actor_id,
        source_revision_id=None,
        origin_kind="app_init",
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=1,
        template_runtime="vite_static",
    )
    app.current_draft_revision_id = created.id
    return created


async def _create_draft_revision_snapshot(
    *,
    db: AsyncSession,
    app: PublishedApp,
    current: PublishedAppRevision,
    actor_id: Optional[UUID],
    files: Dict[str, str],
    entry_file: str,
) -> PublishedAppRevision:
    revision = await create_app_version(
        db,
        app=app,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=entry_file,
        files=files,
        created_by=actor_id,
        source_revision_id=current.id,
        origin_kind="draft_snapshot",
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=_next_build_seq(current),
        template_runtime="vite_static",
    )
    app.current_draft_revision_id = revision.id
    return revision
