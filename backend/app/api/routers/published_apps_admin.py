import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.core.security import create_published_app_preview_token
from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.identity import OrgMembership, OrgRole, User
from app.db.postgres.models.published_apps import (
    BuilderCheckpointType,
    BuilderConversationTurnStatus,
    PublishedApp,
    PublishedAppBuilderConversationTurn,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
    PublishedAppStatus,
)
from app.db.postgres.session import get_db
from app.services.apps_builder_dependency_policy import validate_builder_dependency_policy
from app.services.published_app_bundle_storage import (
    PublishedAppBundleStorage,
    PublishedAppBundleStorageError,
)
from app.services.published_app_draft_dev_runtime import (
    PublishedAppDraftDevRuntimeDisabled,
    PublishedAppDraftDevRuntimeService,
)
from app.services.published_app_templates import (
    build_template_files,
    get_template,
    list_templates,
)


router = APIRouter(prefix="/admin/apps", tags=["published-apps-admin"])
logger = logging.getLogger(__name__)

APP_SLUG_PATTERN = re.compile(r"^[a-z0-9-]{3,64}$")
BUILDER_ALLOWED_DIR_ROOTS = ("src/", "public/")
BUILDER_ALLOWED_ROOT_FILES = {
    "index.html",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}
BUILDER_ALLOWED_ROOT_GLOBS = (
    "vite.config.*",
    "tsconfig*.json",
    "postcss.config.*",
    "tailwind.config.*",
    "vitest.config.*",
    "jest.config.*",
    "playwright.config.*",
    "eslint.config.*",
    "prettier.config.*",
    ".eslintrc.*",
    ".prettierrc.*",
)
BUILDER_ALLOWED_EXTENSIONS = {
    ".html",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".css",
    ".json",
    ".yaml",
    ".yml",
    ".lock",
    ".md",
    ".txt",
    ".svg",
    ".ico",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
}
BUILDER_MAX_FILES = int(os.getenv("BUILDER_MAX_FILES", "200"))
BUILDER_MAX_OPS = int(os.getenv("BUILDER_MAX_OPS", "200"))
BUILDER_MAX_FILE_BYTES = int(os.getenv("BUILDER_MAX_FILE_BYTES", str(256 * 1024)))
BUILDER_MAX_LOCKFILE_BYTES = int(os.getenv("BUILDER_MAX_LOCKFILE_BYTES", str(2 * 1024 * 1024)))
BUILDER_MAX_PROJECT_BYTES = int(os.getenv("BUILDER_MAX_PROJECT_BYTES", str(2 * 1024 * 1024)))
BUILDER_MODEL_NAME = os.getenv("BUILDER_MODEL_NAME", "gpt-5-mini")
BUILDER_MODEL_MAX_RETRIES = int(os.getenv("BUILDER_MODEL_MAX_RETRIES", "2"))
BUILDER_CONTEXT_MAX_FILES = int(os.getenv("BUILDER_CONTEXT_MAX_FILES", "14"))
BUILDER_CONTEXT_MAX_FILE_BYTES = int(os.getenv("BUILDER_CONTEXT_MAX_FILE_BYTES", str(24 * 1024)))
BUILDER_AGENT_MAX_ITERATIONS = int(os.getenv("BUILDER_AGENT_MAX_ITERATIONS", "3"))
BUILDER_AGENT_MAX_SEARCH_RESULTS = int(os.getenv("BUILDER_AGENT_MAX_SEARCH_RESULTS", "8"))
BUILDER_CHAT_COMMAND_TIMEOUT_SECONDS = int(os.getenv("APPS_BUILDER_CHAT_COMMAND_TIMEOUT_SECONDS", "180"))
BUILDER_CHAT_MAX_COMMAND_OUTPUT_BYTES = int(os.getenv("APPS_BUILDER_CHAT_MAX_COMMAND_OUTPUT_BYTES", "12000"))
BUILDER_CHECKPOINT_LIST_LIMIT = int(os.getenv("APPS_BUILDER_CHECKPOINT_LIST_LIMIT", "50"))
IMPORT_RE = re.compile(r'^\s*(?:import|export)\s+(?:[^"\']*?\s+from\s+)?["\']([^"\']+)["\']', re.MULTILINE)
BUILDER_FILE_MENTION_RE = re.compile(r"@([A-Za-z0-9._/\-]+)")
BUILDER_LOCKFILE_NAMES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
PUBLISH_POLL_MAX_DIAGNOSTICS = 12


class PublishedAppResponse(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    name: str
    slug: str
    status: str
    auth_enabled: bool
    auth_providers: List[str]
    template_key: str
    current_draft_revision_id: Optional[str] = None
    current_published_revision_id: Optional[str] = None
    published_url: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None


class PublishedAppTemplateResponse(BaseModel):
    key: str
    name: str
    description: str
    thumbnail: str
    tags: List[str]
    entry_file: str
    style_tokens: Dict[str, str]


class PublishedAppRevisionResponse(BaseModel):
    id: str
    published_app_id: str
    kind: str
    template_key: str
    entry_file: str
    files: Dict[str, str]
    build_status: str
    build_seq: int
    build_error: Optional[str] = None
    build_started_at: Optional[datetime] = None
    build_finished_at: Optional[datetime] = None
    dist_storage_prefix: Optional[str] = None
    dist_manifest: Optional[Dict[str, Any]] = None
    template_runtime: str = "vite_static"
    compiled_bundle: Optional[str] = None
    bundle_hash: Optional[str] = None
    source_revision_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime


class BuilderStateResponse(BaseModel):
    app: PublishedAppResponse
    templates: List[PublishedAppTemplateResponse]
    current_draft_revision: Optional[PublishedAppRevisionResponse] = None
    current_published_revision: Optional[PublishedAppRevisionResponse] = None
    preview_token: Optional[str] = None
    draft_dev: Optional["DraftDevSessionResponse"] = None


class BuilderPatchOp(BaseModel):
    op: Literal["upsert_file", "delete_file", "rename_file", "set_entry_file"]
    path: Optional[str] = None
    content: Optional[str] = None
    from_path: Optional[str] = None
    to_path: Optional[str] = None
    entry_file: Optional[str] = None


class CreatePublishedAppRequest(BaseModel):
    name: str
    slug: Optional[str] = None
    agent_id: UUID
    template_key: str = "chat-classic"
    auth_enabled: bool = True
    auth_providers: List[str] = Field(default_factory=lambda: ["password"])


class UpdatePublishedAppRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    agent_id: Optional[UUID] = None
    auth_enabled: Optional[bool] = None
    auth_providers: Optional[List[str]] = None
    status: Optional[str] = None


class CreateBuilderRevisionRequest(BaseModel):
    base_revision_id: Optional[UUID] = None
    operations: List[BuilderPatchOp] = Field(default_factory=list)
    files: Optional[Dict[str, str]] = None
    entry_file: Optional[str] = None


class TemplateResetRequest(BaseModel):
    template_key: str


class BuilderChatRequest(BaseModel):
    input: str
    base_revision_id: Optional[UUID] = None


class BuilderValidationResponse(BaseModel):
    ok: bool
    entry_file: str
    file_count: int
    diagnostics: List[Dict[str, str]] = Field(default_factory=list)


class RevisionBuildStatusResponse(BaseModel):
    revision_id: str
    build_status: str
    build_seq: int
    build_error: Optional[str] = None
    build_started_at: Optional[datetime] = None
    build_finished_at: Optional[datetime] = None
    dist_storage_prefix: Optional[str] = None
    dist_manifest: Optional[Dict[str, Any]] = None
    template_runtime: str = "vite_static"


class DraftDevSessionResponse(BaseModel):
    session_id: str
    app_id: str
    revision_id: Optional[str] = None
    status: str
    preview_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    idle_timeout_seconds: int = 180
    last_activity_at: Optional[datetime] = None
    last_error: Optional[str] = None


class DraftDevSyncRequest(BaseModel):
    files: Dict[str, str]
    entry_file: str
    revision_id: Optional[UUID] = None


class PublishJobResponse(BaseModel):
    job_id: str
    app_id: str
    status: str
    source_revision_id: Optional[str] = None
    saved_draft_revision_id: Optional[str] = None
    published_revision_id: Optional[str] = None
    error: Optional[str] = None
    diagnostics: List[Dict[str, str]] = Field(default_factory=list)
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class PublishJobStatusResponse(PublishJobResponse):
    pass


class PublishRequest(BaseModel):
    base_revision_id: Optional[UUID] = None
    files: Optional[Dict[str, str]] = None
    entry_file: Optional[str] = None


class BuilderConversationTurnResponse(BaseModel):
    id: str
    published_app_id: str
    revision_id: Optional[str] = None
    result_revision_id: Optional[str] = None
    request_id: str
    status: str
    user_prompt: str
    assistant_summary: Optional[str] = None
    assistant_rationale: Optional[str] = None
    assistant_assumptions: List[str] = Field(default_factory=list)
    patch_operations: List[Dict[str, Any]] = Field(default_factory=list)
    tool_trace: List[Dict[str, Any]] = Field(default_factory=list)
    tool_summary: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: List[Dict[str, str]] = Field(default_factory=list)
    failure_code: Optional[str] = None
    checkpoint_type: Optional[str] = None
    checkpoint_label: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime


class BuilderCheckpointResponse(BaseModel):
    turn_id: str
    request_id: str
    revision_id: str
    source_revision_id: Optional[str] = None
    checkpoint_type: str
    checkpoint_label: Optional[str] = None
    assistant_summary: Optional[str] = None
    created_at: datetime


class BuilderUndoRequest(BaseModel):
    base_revision_id: Optional[UUID] = None


class BuilderUndoResponse(BaseModel):
    revision: PublishedAppRevisionResponse
    restored_from_revision_id: str
    checkpoint_turn_id: str
    request_id: str


class BuilderRevertFileRequest(BaseModel):
    path: str
    from_revision_id: UUID
    base_revision_id: Optional[UUID] = None


class BuilderRevertFileResponse(BaseModel):
    revision: PublishedAppRevisionResponse
    reverted_path: str
    from_revision_id: str
    request_id: str


class BuilderModelPatchPlan(BaseModel):
    operations: List[BuilderPatchOp] = Field(default_factory=list)
    summary: str = "prepared a draft update"
    rationale: str = ""
    assumptions: List[str] = Field(default_factory=list)


class BuilderPatchGenerationResult(BaseModel):
    operations: List[BuilderPatchOp] = Field(default_factory=list)
    summary: str = "prepared a draft update"
    rationale: str = ""
    assumptions: List[str] = Field(default_factory=list)


def _apps_base_domain() -> str:
    return os.getenv("APPS_BASE_DOMAIN", "apps.localhost")


def _apps_url_scheme() -> str:
    configured = (os.getenv("APPS_URL_SCHEME") or "").strip().lower()
    if configured in {"http", "https"}:
        return configured
    return "https"


def _apps_url_port() -> str:
    configured = (os.getenv("APPS_URL_PORT") or "").strip()
    if configured:
        return configured if configured.startswith(":") else f":{configured}"
    return ""


def _build_published_url(slug: str) -> str:
    return f"{_apps_url_scheme()}://{slug}.{_apps_base_domain()}{_apps_url_port()}"


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]", "-", value.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        normalized = "app"
    if len(normalized) < 3:
        normalized = f"{normalized}-app"
    return normalized[:64]


def _validate_template_key(template_key: str) -> str:
    key = template_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="template_key is required")
    try:
        get_template(key)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unsupported template_key: {key}")
    return key


def _validate_providers(providers: List[str]) -> List[str]:
    normalized = [p.strip().lower() for p in providers if p and p.strip()]
    if not normalized:
        raise HTTPException(status_code=400, detail="At least one auth provider must be configured")
    allowed = {"password", "google"}
    invalid = [p for p in normalized if p not in allowed]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported auth providers: {', '.join(invalid)}")
    return sorted(set(normalized))


def _app_to_response(app: PublishedApp) -> PublishedAppResponse:
    return PublishedAppResponse(
        id=str(app.id),
        tenant_id=str(app.tenant_id),
        agent_id=str(app.agent_id),
        name=app.name,
        slug=app.slug,
        status=app.status.value if hasattr(app.status, "value") else str(app.status),
        auth_enabled=bool(app.auth_enabled),
        auth_providers=list(app.auth_providers or []),
        template_key=app.template_key or "chat-classic",
        current_draft_revision_id=str(app.current_draft_revision_id) if app.current_draft_revision_id else None,
        current_published_revision_id=str(app.current_published_revision_id) if app.current_published_revision_id else None,
        published_url=app.published_url,
        created_by=str(app.created_by) if app.created_by else None,
        created_at=app.created_at,
        updated_at=app.updated_at,
        published_at=app.published_at,
    )


def _template_to_response(template) -> PublishedAppTemplateResponse:
    return PublishedAppTemplateResponse(
        key=template.key,
        name=template.name,
        description=template.description,
        thumbnail=template.thumbnail,
        tags=list(template.tags),
        entry_file=template.entry_file,
        style_tokens=dict(template.style_tokens),
    )


def _revision_to_response(revision: PublishedAppRevision) -> PublishedAppRevisionResponse:
    return PublishedAppRevisionResponse(
        id=str(revision.id),
        published_app_id=str(revision.published_app_id),
        kind=revision.kind.value if hasattr(revision.kind, "value") else str(revision.kind),
        template_key=revision.template_key,
        entry_file=revision.entry_file,
        files=dict(revision.files or {}),
        build_status=revision.build_status.value if hasattr(revision.build_status, "value") else str(revision.build_status),
        build_seq=int(revision.build_seq or 0),
        build_error=revision.build_error,
        build_started_at=revision.build_started_at,
        build_finished_at=revision.build_finished_at,
        dist_storage_prefix=revision.dist_storage_prefix,
        dist_manifest=dict(revision.dist_manifest or {}) if revision.dist_manifest else None,
        template_runtime=revision.template_runtime or "vite_static",
        compiled_bundle=revision.compiled_bundle,
        bundle_hash=revision.bundle_hash,
        source_revision_id=str(revision.source_revision_id) if revision.source_revision_id else None,
        created_by=str(revision.created_by) if revision.created_by else None,
        created_at=revision.created_at,
    )


def _revision_build_status_to_response(revision: PublishedAppRevision) -> RevisionBuildStatusResponse:
    return RevisionBuildStatusResponse(
        revision_id=str(revision.id),
        build_status=revision.build_status.value if hasattr(revision.build_status, "value") else str(revision.build_status),
        build_seq=int(revision.build_seq or 0),
        build_error=revision.build_error,
        build_started_at=revision.build_started_at,
        build_finished_at=revision.build_finished_at,
        dist_storage_prefix=revision.dist_storage_prefix,
        dist_manifest=dict(revision.dist_manifest or {}) if revision.dist_manifest else None,
        template_runtime=revision.template_runtime or "vite_static",
    )


def _draft_dev_session_to_response(session: PublishedAppDraftDevSession) -> DraftDevSessionResponse:
    return DraftDevSessionResponse(
        session_id=str(session.id),
        app_id=str(session.published_app_id),
        revision_id=str(session.revision_id) if session.revision_id else None,
        status=session.status.value if hasattr(session.status, "value") else str(session.status),
        preview_url=session.preview_url,
        expires_at=session.expires_at,
        idle_timeout_seconds=int(session.idle_timeout_seconds or 180),
        last_activity_at=session.last_activity_at,
        last_error=session.last_error,
    )


def _publish_job_to_response(job: PublishedAppPublishJob) -> PublishJobResponse:
    diagnostics = list(job.diagnostics or [])
    normalized = [item for item in diagnostics if isinstance(item, dict)]
    return PublishJobResponse(
        job_id=str(job.id),
        app_id=str(job.published_app_id),
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        source_revision_id=str(job.source_revision_id) if job.source_revision_id else None,
        saved_draft_revision_id=str(job.saved_draft_revision_id) if job.saved_draft_revision_id else None,
        published_revision_id=str(job.published_revision_id) if job.published_revision_id else None,
        error=job.error,
        diagnostics=normalized[:PUBLISH_POLL_MAX_DIAGNOSTICS],
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


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
        select(PublishedAppDraftDevSession).where(
            and_(
                PublishedAppDraftDevSession.published_app_id == app_id,
                PublishedAppDraftDevSession.user_id == user_id,
            )
        ).limit(1)
    )
    return result.scalar_one_or_none()


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


async def _ensure_current_draft_revision(db: AsyncSession, app: PublishedApp, actor_id: Optional[UUID]) -> PublishedAppRevision:
    draft = await _get_revision(db, app.current_draft_revision_id)
    if draft is not None:
        return draft

    files = build_template_files(app.template_key or "chat-classic")
    created = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key or "chat-classic",
        entry_file=get_template(app.template_key or "chat-classic").entry_file,
        files=files,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=1,
        build_error=None,
        build_started_at=None,
        build_finished_at=None,
        dist_storage_prefix=None,
        dist_manifest=None,
        template_runtime="vite_static",
        compiled_bundle=None,
        bundle_hash=sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
        source_revision_id=None,
        created_by=actor_id,
    )
    db.add(created)
    await db.flush()
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
    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=entry_file,
        files=files,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=_next_build_seq(current),
        build_error=None,
        build_started_at=None,
        build_finished_at=None,
        dist_storage_prefix=None,
        dist_manifest=None,
        template_runtime="vite_static",
        compiled_bundle=None,
        bundle_hash=sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
        source_revision_id=current.id,
        created_by=actor_id,
    )
    db.add(revision)
    await db.flush()
    app.current_draft_revision_id = revision.id
    return revision


def _builder_policy_error(message: str, *, field: Optional[str] = None) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "BUILDER_PATCH_POLICY_VIOLATION",
            "message": message,
            "field": field,
        },
    )


def _builder_compile_error(message: str, diagnostics: Optional[List[Dict[str, str]]] = None) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "BUILDER_COMPILE_FAILED",
            "message": message,
            "diagnostics": diagnostics or [],
        },
    )


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _builder_model_patch_generation_enabled() -> bool:
    return _env_flag("BUILDER_MODEL_PATCH_GENERATION_ENABLED", False)


def _builder_agentic_loop_enabled() -> bool:
    return _env_flag("BUILDER_AGENTIC_LOOP_ENABLED", False)


def _builder_targeted_tests_enabled() -> bool:
    return _env_flag("APPS_BUILDER_TARGETED_TESTS_ENABLED", False)


def _builder_chat_sandbox_tools_enabled() -> bool:
    return _env_flag("APPS_BUILDER_CHAT_SANDBOX_TOOLS_ENABLED", False)


def _builder_chat_commands_enabled() -> bool:
    return _env_flag("APPS_BUILDER_CHAT_COMMANDS_ENABLED", False)


def _builder_chat_worker_precheck_enabled() -> bool:
    return _env_flag("APPS_BUILDER_CHAT_WORKER_PRECHECK_ENABLED", False)


def _builder_chat_command_allowlist() -> List[List[str]]:
    raw = (os.getenv("APPS_BUILDER_CHAT_COMMAND_ALLOWLIST") or "").strip()
    defaults = [
        ["npm", "run", "build"],
        ["npm", "run", "lint"],
        ["npm", "run", "typecheck"],
        ["npm", "run", "test", "--", "--run", "--passWithNoTests"],
    ]
    if not raw:
        return defaults
    commands: List[List[str]] = []
    for item in raw.split(";"):
        tokens = [token for token in item.strip().split(" ") if token]
        if tokens:
            commands.append(tokens)
    return commands or defaults


def _is_allowed_sandbox_command(command: List[str], *, allowlist: List[List[str]]) -> bool:
    if not command:
        return False
    # Reject obvious shell metacharacter payloads. Command is tokenized and executed without shell.
    forbidden = {"|", "&&", "||", ";", "$(", "`", ">", "<"}
    for token in command:
        if any(mark in token for mark in forbidden):
            return False
    return any(command == allowed for allowed in allowlist)


def _new_builder_request_id() -> str:
    return uuid4().hex


def _stream_event_payload(
    *,
    event: str,
    stage: str,
    request_id: str,
    data: Optional[Dict[str, Any]] = None,
    diagnostics: Optional[List[Dict[str, str]]] = None,
    include_done_type: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "event": event,
        "stage": stage,
        "request_id": request_id,
    }
    if data is not None:
        payload["data"] = data
    if diagnostics:
        payload["diagnostics"] = diagnostics
    if include_done_type:
        payload["type"] = "done"
    return payload


def _stream_event_sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _extract_http_error_details(exc: HTTPException) -> tuple[str, List[Dict[str, str]]]:
    detail = exc.detail
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("code") or "builder operation failed")
        raw_diagnostics = detail.get("diagnostics")
        diagnostics: List[Dict[str, str]] = []
        if isinstance(raw_diagnostics, list):
            diagnostics = [item for item in raw_diagnostics if isinstance(item, dict)]
        if not diagnostics and message:
            diagnostics = [{"message": message}]
        return message, diagnostics
    return str(detail), [{"message": str(detail)}]


def _extract_http_error_code(exc: HTTPException) -> Optional[str]:
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code")
        if code:
            return str(code)
    return None


def _next_build_seq(previous: Optional[PublishedAppRevision]) -> int:
    if previous is None:
        return 1
    return int(previous.build_seq or 0) + 1


def _builder_auto_enqueue_enabled() -> bool:
    return _env_flag("APPS_BUILDER_BUILD_AUTOMATION_ENABLED", False)


def _builder_worker_build_gate_enabled() -> bool:
    return _env_flag("APPS_BUILDER_WORKER_BUILD_GATE_ENABLED", False)


def _publish_full_build_enabled() -> bool:
    return _env_flag("APPS_PUBLISH_FULL_BUILD_ENABLED", True)


def _publish_job_eager_enabled() -> bool:
    return _env_flag("APPS_PUBLISH_JOB_EAGER", False)


def _mark_revision_build_enqueue_failed(
    *,
    revision: PublishedAppRevision,
    reason: str,
) -> None:
    normalized_reason = (reason or "").strip()
    if len(normalized_reason) > 4000:
        normalized_reason = f"{normalized_reason[:4000]}... [truncated]"
    revision.build_status = PublishedAppRevisionBuildStatus.failed
    revision.build_error = normalized_reason or "Build enqueue failed"
    revision.build_started_at = None
    revision.build_finished_at = datetime.now(timezone.utc)
    revision.dist_storage_prefix = None
    revision.dist_manifest = None


def _enqueue_revision_build(
    *,
    revision: PublishedAppRevision,
    app: PublishedApp,
    build_kind: str,
) -> Optional[str]:
    if not _builder_auto_enqueue_enabled():
        return (
            "Build automation is disabled (`APPS_BUILDER_BUILD_AUTOMATION_ENABLED=0`). "
            "Enable it and retry build."
        )
    try:
        from app.workers.tasks import build_published_app_revision_task
    except Exception as exc:
        return f"Build worker task import failed: {exc}"

    try:
        build_published_app_revision_task.delay(
            revision_id=str(revision.id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            slug=app.slug,
            build_kind=build_kind,
        )
    except Exception as exc:
        logger.warning(
            "Failed to enqueue published app build task",
            extra={
                "revision_id": str(revision.id),
                "app_id": str(app.id),
                "build_kind": build_kind,
                "error": str(exc),
            },
        )
        return f"Failed to enqueue build task: {exc}"
    return None


def _enqueue_publish_job(
    *,
    job: PublishedAppPublishJob,
) -> Optional[str]:
    try:
        from app.workers.tasks import publish_published_app_task
    except Exception as exc:
        return f"Publish worker task import failed: {exc}"

    if _publish_job_eager_enabled():
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    publish_published_app_task.run,
                    str(job.id),
                )
                future.result()
        except Exception as exc:
            logger.warning(
                "Failed to run published app publish task eagerly",
                extra={
                    "publish_job_id": str(job.id),
                    "app_id": str(job.published_app_id),
                    "error": str(exc),
                },
            )
            return f"Failed to run publish task eagerly: {exc}"
        return None

    try:
        publish_published_app_task.delay(
            job_id=str(job.id),
        )
    except Exception as exc:
        logger.warning(
            "Failed to enqueue published app publish task",
            extra={
                "publish_job_id": str(job.id),
                "app_id": str(job.published_app_id),
                "error": str(exc),
            },
        )
        return f"Failed to enqueue publish task: {exc}"
    return None


def _summarize_dist_manifest(dist_manifest: Dict[str, Any]) -> Dict[str, Any]:
    assets = dist_manifest.get("assets")
    normalized_assets = assets if isinstance(assets, list) else []
    total_bytes = 0
    asset_paths: List[str] = []
    for item in normalized_assets:
        if not isinstance(item, dict):
            continue
        total_bytes += int(item.get("size") or 0)
        path = item.get("path")
        if isinstance(path, str) and path:
            asset_paths.append(path)
    return {
        "entry_html": str(dist_manifest.get("entry_html") or "index.html"),
        "asset_count": len(normalized_assets),
        "total_bytes": total_bytes,
        "asset_paths_preview": asset_paths[:12],
    }


async def _run_worker_build_preflight(
    files: Dict[str, str],
    *,
    include_dist_manifest: bool = False,
) -> Optional[Dict[str, Any]]:
    from app.workers.tasks import _build_dist_manifest, _materialize_project_files, _run_subprocess

    npm_ci_timeout = int(os.getenv("APPS_BUILD_NPM_CI_TIMEOUT_SECONDS", "300"))
    npm_build_timeout = int(os.getenv("APPS_BUILD_NPM_BUILD_TIMEOUT_SECONDS", "300"))

    with tempfile.TemporaryDirectory(prefix="apps-builder-preflight-") as temp_dir:
        project_dir = Path(temp_dir)
        _materialize_project_files(project_dir, files)

        has_lockfile = (project_dir / "package-lock.json").exists()
        install_command = ["npm", "ci"] if has_lockfile else ["npm", "install", "--no-audit", "--no-fund"]
        install_code, install_stdout, install_stderr = await _run_subprocess(
            install_command,
            cwd=project_dir,
            timeout_seconds=npm_ci_timeout,
        )
        if install_code != 0:
            install_name = "npm ci" if has_lockfile else "npm install"
            raise RuntimeError(
                f"`{install_name}` failed with exit code {install_code}\n{install_stderr or install_stdout}"
            )

        build_code, build_stdout, build_stderr = await _run_subprocess(
            ["npm", "run", "build"],
            cwd=project_dir,
            timeout_seconds=npm_build_timeout,
        )
        if build_code != 0:
            raise RuntimeError(
                f"`npm run build` failed with exit code {build_code}\n{build_stderr or build_stdout}"
            )

        dist_dir = project_dir / "dist"
        if not dist_dir.exists() or not dist_dir.is_dir():
            raise RuntimeError("Build succeeded but dist directory was not produced")
        if include_dist_manifest:
            return _build_dist_manifest(dist_dir)
    return None


async def _validate_worker_build_gate_or_raise(files: Dict[str, str]) -> None:
    if not _builder_worker_build_gate_enabled():
        return
    try:
        await _run_worker_build_preflight(files)
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).strip() or "Worker build validation failed"
        if len(message) > 4000:
            message = message[:4000] + "... [truncated]"
        raise _builder_compile_error(
            "Worker build validation failed",
            diagnostics=[{"message": message}],
        )


def _promote_revision_dist_artifacts(
    *,
    app: PublishedApp,
    source_revision: PublishedAppRevision,
    destination_revision: PublishedAppRevision,
) -> Optional[str]:
    source_prefix = (source_revision.dist_storage_prefix or "").strip()
    if not source_prefix:
        return None

    storage = PublishedAppBundleStorage.from_env()
    destination_prefix = PublishedAppBundleStorage.build_revision_dist_prefix(
        tenant_id=str(app.tenant_id),
        app_id=str(app.id),
        revision_id=str(destination_revision.id),
    )
    storage.copy_prefix(
        source_prefix=source_prefix,
        destination_prefix=destination_prefix,
    )
    return destination_prefix


def _truncate_for_context(content: str, *, max_bytes: int = BUILDER_CONTEXT_MAX_FILE_BYTES) -> str:
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return content
    clipped = encoded[:max_bytes]
    while clipped:
        try:
            decoded = clipped.decode("utf-8")
            return decoded + "\n/* ...truncated for prompt budget... */"
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return "/* ...truncated for prompt budget... */"


def _collect_local_imports(path: str, files: Dict[str, str]) -> List[str]:
    source = files.get(path, "")
    neighbors: List[str] = []
    for spec in IMPORT_RE.findall(source):
        import_path = (spec or "").strip()
        if not import_path.startswith("."):
            continue
        resolved = _resolve_local_project_import(import_path, path, files)
        if resolved:
            neighbors.append(resolved)
    return neighbors


def _select_builder_context_paths(
    files: Dict[str, str],
    entry_file: str,
    user_prompt: str,
    *,
    recent_paths: Optional[List[str]] = None,
) -> List[str]:
    selected: List[str] = []

    def add(path: str) -> None:
        if path in files and path not in selected:
            selected.append(path)

    add(entry_file)
    add("src/main.tsx")
    add("src/App.tsx")
    add("src/theme.ts")
    for focus_path in _extract_prompt_focus_paths(files, user_prompt):
        add(focus_path)

    queue = list(selected)
    visited: set[str] = set()
    while queue and len(selected) < BUILDER_CONTEXT_MAX_FILES:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for neighbor in _collect_local_imports(current, files):
            if len(selected) >= BUILDER_CONTEXT_MAX_FILES:
                break
            if neighbor not in selected:
                selected.append(neighbor)
                queue.append(neighbor)

    for path in recent_paths or []:
        if len(selected) >= BUILDER_CONTEXT_MAX_FILES:
            break
        add(path)

    prompt_terms = [
        term
        for term in re.findall(r"[a-zA-Z_]{4,}", user_prompt.lower())
        if term not in {"that", "with", "from", "this", "make", "into", "change"}
    ][:8]
    if prompt_terms and len(selected) < BUILDER_CONTEXT_MAX_FILES:
        for path in sorted(files.keys()):
            if len(selected) >= BUILDER_CONTEXT_MAX_FILES:
                break
            lowered_path = path.lower()
            source = files.get(path, "").lower()
            if any(term in lowered_path or term in source for term in prompt_terms):
                add(path)

    if len(selected) < BUILDER_CONTEXT_MAX_FILES:
        for path in sorted(files.keys()):
            if len(selected) >= BUILDER_CONTEXT_MAX_FILES:
                break
            add(path)
    return selected


def _extract_prompt_focus_paths(files: Dict[str, str], user_prompt: str, *, max_paths: int = 6) -> List[str]:
    focus_paths: List[str] = []
    candidates: List[str] = []

    for raw_match in BUILDER_FILE_MENTION_RE.findall(user_prompt or ""):
        cleaned = raw_match.strip().strip(".,:;!?)]}>")
        if cleaned:
            candidates.append(cleaned)

    for candidate in candidates:
        normalized_input = candidate[2:] if candidate.startswith("./") else candidate
        normalized_path: Optional[str] = None
        try:
            normalized_path = _normalize_builder_path(normalized_input)
        except HTTPException:
            normalized_path = None

        if normalized_path and normalized_path in files and normalized_path not in focus_paths:
            focus_paths.append(normalized_path)
            if len(focus_paths) >= max_paths:
                break
            continue

        basename = PurePosixPath(normalized_input).name
        if not basename:
            continue
        basename_matches = [
            path
            for path in sorted(files.keys())
            if PurePosixPath(path).name == basename
        ]
        if len(basename_matches) == 1 and basename_matches[0] not in focus_paths:
            focus_paths.append(basename_matches[0])
            if len(focus_paths) >= max_paths:
                break

    return focus_paths[:max_paths]


def _serialize_patch_ops(operations: List[BuilderPatchOp]) -> List[Dict[str, Any]]:
    return [op.model_dump(exclude_none=True) for op in operations]


def _builder_conversation_to_response(turn: PublishedAppBuilderConversationTurn) -> BuilderConversationTurnResponse:
    return BuilderConversationTurnResponse(
        id=str(turn.id),
        published_app_id=str(turn.published_app_id),
        revision_id=str(turn.revision_id) if turn.revision_id else None,
        result_revision_id=str(turn.result_revision_id) if turn.result_revision_id else None,
        request_id=turn.request_id,
        status=turn.status.value if hasattr(turn.status, "value") else str(turn.status),
        user_prompt=turn.user_prompt,
        assistant_summary=turn.assistant_summary,
        assistant_rationale=turn.assistant_rationale,
        assistant_assumptions=list(turn.assistant_assumptions or []),
        patch_operations=list(turn.patch_operations or []),
        tool_trace=list(turn.tool_trace or []),
        tool_summary=dict(turn.tool_summary or {}),
        diagnostics=list(turn.diagnostics or []),
        failure_code=turn.failure_code,
        checkpoint_type=turn.checkpoint_type.value if hasattr(turn.checkpoint_type, "value") else str(turn.checkpoint_type),
        checkpoint_label=turn.checkpoint_label,
        created_by=str(turn.created_by) if turn.created_by else None,
        created_at=turn.created_at,
    )


def _build_tool_summary(trace_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {
        "total": 0,
        "failed": 0,
        "completed": 0,
        "tools": [],
    }
    tools_seen: List[str] = []
    for event in trace_events:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "")
        if event_name not in {"tool_started", "tool_completed", "tool_failed"}:
            continue
        summary["total"] += 1
        data = event.get("data")
        if isinstance(data, dict):
            tool_name = str(data.get("tool") or "").strip()
            if tool_name and tool_name not in tools_seen:
                tools_seen.append(tool_name)
        if event_name == "tool_failed":
            summary["failed"] += 1
        if event_name == "tool_completed":
            summary["completed"] += 1
    summary["tools"] = tools_seen
    return summary


def _builder_checkpoint_to_response(turn: PublishedAppBuilderConversationTurn) -> BuilderCheckpointResponse:
    if turn.result_revision_id is None:
        raise ValueError("Checkpoint turn is missing result revision")
    return BuilderCheckpointResponse(
        turn_id=str(turn.id),
        request_id=turn.request_id,
        revision_id=str(turn.result_revision_id),
        source_revision_id=None,
        checkpoint_type=turn.checkpoint_type.value if hasattr(turn.checkpoint_type, "value") else str(turn.checkpoint_type),
        checkpoint_label=turn.checkpoint_label,
        assistant_summary=turn.assistant_summary,
        created_at=turn.created_at,
    )


async def _persist_builder_conversation_turn(
    db: AsyncSession,
    *,
    app_id: UUID,
    revision_id: Optional[UUID],
    actor_id: Optional[UUID],
    request_id: str,
    user_prompt: str,
    status: BuilderConversationTurnStatus,
    generation_result: Optional[BuilderPatchGenerationResult] = None,
    trace_events: Optional[List[Dict[str, Any]]] = None,
    diagnostics: Optional[List[Dict[str, str]]] = None,
    failure_code: Optional[str] = None,
    result_revision_id: Optional[UUID] = None,
    checkpoint_type: BuilderCheckpointType = BuilderCheckpointType.auto_run,
    checkpoint_label: Optional[str] = None,
) -> None:
    trace = list(trace_events or [])
    turn = PublishedAppBuilderConversationTurn(
        published_app_id=app_id,
        revision_id=revision_id,
        result_revision_id=result_revision_id,
        request_id=request_id,
        status=status,
        user_prompt=user_prompt,
        assistant_summary=generation_result.summary if generation_result else None,
        assistant_rationale=generation_result.rationale if generation_result else None,
        assistant_assumptions=list(generation_result.assumptions) if generation_result else [],
        patch_operations=_serialize_patch_ops(generation_result.operations) if generation_result else [],
        tool_trace=trace,
        tool_summary=_build_tool_summary(trace),
        diagnostics=list(diagnostics or []),
        failure_code=failure_code,
        checkpoint_type=checkpoint_type,
        checkpoint_label=checkpoint_label,
        created_by=actor_id,
    )
    db.add(turn)
    await db.flush()


def _build_builder_context_snapshot(
    files: Dict[str, str],
    entry_file: str,
    user_prompt: str,
    *,
    recent_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    selected_paths = _select_builder_context_paths(
        files,
        entry_file,
        user_prompt,
        recent_paths=recent_paths,
    )
    selected_files = [
        {"path": path, "content": _truncate_for_context(files[path])}
        for path in selected_paths
    ]
    return {
        "entry_file": entry_file,
        "file_count": len(files),
        "selected_paths": selected_paths,
        "selected_files": selected_files,
    }


def _extract_openai_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    fragments: List[str] = []
    output_items = getattr(response, "output", None)
    if not isinstance(output_items, list):
        return ""

    for item in output_items:
        content_items = getattr(item, "content", None)
        if content_items is None and isinstance(item, dict):
            content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for part in content_items:
            part_type = getattr(part, "type", None)
            if part_type is None and isinstance(part, dict):
                part_type = part.get("type")
            if part_type not in {"output_text", "text"}:
                continue
            text_value = getattr(part, "text", None)
            if text_value is None and isinstance(part, dict):
                text_value = part.get("text") or part.get("value")
            if text_value:
                fragments.append(str(text_value))
    return "".join(fragments).strip()


async def _request_builder_model_patch_plan(
    *,
    user_prompt: str,
    files: Dict[str, str],
    entry_file: str,
    repair_feedback: List[str],
    recent_paths: Optional[List[str]] = None,
) -> BuilderModelPatchPlan:
    openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for model-backed builder patch generation")

    try:
        from openai import AsyncOpenAI
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError("openai package is required for model-backed builder patch generation") from exc

    context_snapshot = _build_builder_context_snapshot(
        files,
        entry_file,
        user_prompt,
        recent_paths=recent_paths,
    )
    model_input = {
        "task": user_prompt,
        "contract": {
            "operations": "BuilderPatchOp[]",
            "summary": "short user-facing summary",
            "rationale": "concise implementation rationale",
            "assumptions": "list of assumptions",
        },
        "repair_feedback": repair_feedback[-4:],
        "context": context_snapshot,
    }
    system_prompt = (
        "You generate safe frontend patch operations.\n"
        "Return only strict JSON (no markdown) with keys: operations, summary, rationale, assumptions.\n"
        "Each operation must be one of: upsert_file, delete_file, rename_file, set_entry_file.\n"
        "Use paths under src/, public/, or allowed Vite root files only."
    )

    client = AsyncOpenAI(api_key=openai_api_key)
    response = await client.responses.create(
        model=BUILDER_MODEL_NAME,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(model_input)},
        ],
        max_output_tokens=1400,
    )
    raw_text = _extract_openai_response_text(response)
    if not raw_text:
        raise RuntimeError("Model returned an empty patch response")

    try:
        return BuilderModelPatchPlan.model_validate_json(raw_text)
    except ValidationError as exc:
        raise ValueError(f"Model output failed schema validation: {exc}") from exc


async def _generate_builder_patch_with_model(
    *,
    user_prompt: str,
    files: Dict[str, str],
    entry_file: str,
    repair_feedback: Optional[List[str]] = None,
    recent_paths: Optional[List[str]] = None,
) -> BuilderPatchGenerationResult:
    feedback = list(repair_feedback or [])
    last_errors: List[Dict[str, str]] = []

    for _ in range(BUILDER_MODEL_MAX_RETRIES + 1):
        try:
            patch_plan = await _request_builder_model_patch_plan(
                user_prompt=user_prompt,
                files=files,
                entry_file=entry_file,
                repair_feedback=feedback,
                recent_paths=recent_paths,
            )
        except (RuntimeError, ValueError) as exc:
            message = str(exc)
            feedback.append(message)
            last_errors.append({"message": message})
            continue

        if not patch_plan.operations:
            message = "Model returned zero operations"
            feedback.append(message)
            last_errors.append({"message": message})
            continue

        try:
            _apply_patch_operations(files, entry_file, patch_plan.operations)
        except HTTPException as exc:
            message, diagnostics = _extract_http_error_details(exc)
            feedback.append(message)
            last_errors.extend(diagnostics)
            continue

        summary = _sanitize_prompt_text(patch_plan.summary, 180) or "prepared a draft update"
        rationale = _sanitize_prompt_text(patch_plan.rationale, 400)
        assumptions = [
            _sanitize_prompt_text(item, 180)
            for item in patch_plan.assumptions
            if _sanitize_prompt_text(item, 180)
        ]
        return BuilderPatchGenerationResult(
            operations=patch_plan.operations,
            summary=summary,
            rationale=rationale,
            assumptions=assumptions,
        )

    raise _builder_compile_error(
        "Model patch generation failed",
        diagnostics=last_errors[-6:] or [{"message": "Model output could not be validated"}],
    )


def _builder_tool_list_files(files: Dict[str, str]) -> Dict[str, Any]:
    paths = sorted(files.keys())
    return {"count": len(paths), "paths": paths[:BUILDER_CONTEXT_MAX_FILES]}


def _builder_tool_read_file(files: Dict[str, str], path: str) -> Dict[str, Any]:
    if path not in files:
        return {"ok": False, "path": path, "message": "file not found"}
    content = files[path]
    return {
        "ok": True,
        "path": path,
        "size_bytes": len(content.encode("utf-8")),
        "preview": _truncate_for_context(content, max_bytes=min(1024, BUILDER_CONTEXT_MAX_FILE_BYTES)),
    }


def _builder_tool_search_code(files: Dict[str, str], query: str) -> Dict[str, Any]:
    needle = query.strip().lower()
    if not needle:
        return {"query": query, "matches": []}
    matches: List[Dict[str, Any]] = []
    for path in sorted(files.keys()):
        lines = files[path].splitlines()
        for index, line in enumerate(lines, start=1):
            if needle in line.lower():
                matches.append(
                    {
                        "path": path,
                        "line": index,
                        "preview": line[:180],
                    }
                )
                if len(matches) >= BUILDER_AGENT_MAX_SEARCH_RESULTS:
                    return {"query": query, "matches": matches}
    return {"query": query, "matches": matches}


def _builder_tool_apply_patch_dry_run(
    files: Dict[str, str],
    entry_file: str,
    operations: List[BuilderPatchOp],
) -> Dict[str, Any]:
    try:
        next_files, next_entry = _apply_patch_operations(files, entry_file, operations)
    except HTTPException as exc:
        message, diagnostics = _extract_http_error_details(exc)
        return {"ok": False, "message": message, "diagnostics": diagnostics}
    return {
        "ok": True,
        "entry_file": next_entry,
        "file_count": len(next_files),
        "diagnostics": [],
    }


def _builder_tool_compile_project(files: Dict[str, str], entry_file: str) -> Dict[str, Any]:
    try:
        diagnostics = _validate_builder_project_or_raise(files, entry_file)
    except HTTPException as exc:
        message, bad_diagnostics = _extract_http_error_details(exc)
        return {"ok": False, "message": message, "diagnostics": bad_diagnostics}
    return {"ok": True, "diagnostics": diagnostics}


def _looks_like_test_file(path: str) -> bool:
    lowered = path.lower()
    if "/__tests__/" in lowered:
        return True
    return lowered.endswith(
        (
            ".test.ts",
            ".test.tsx",
            ".test.js",
            ".test.jsx",
            ".test.mts",
            ".test.cts",
            ".spec.ts",
            ".spec.tsx",
            ".spec.js",
            ".spec.jsx",
            ".spec.mts",
            ".spec.cts",
        )
    )


def _read_package_scripts(files: Dict[str, str]) -> Dict[str, str]:
    package_source = files.get("package.json")
    if not isinstance(package_source, str) or not package_source.strip():
        return {}
    try:
        payload = json.loads(package_source)
    except json.JSONDecodeError:
        return {}
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    normalized: Dict[str, str] = {}
    for key, value in scripts.items():
        if isinstance(key, str) and isinstance(value, str):
            normalized[key] = value
    return normalized


def _select_test_script(files: Dict[str, str]) -> Optional[str]:
    scripts = _read_package_scripts(files)
    for key in ("test", "test:unit", "test:ci"):
        if key in scripts:
            return key
    return None


def _test_related_paths(files: Dict[str, str], changed_paths: List[str]) -> List[str]:
    test_files = [path for path in sorted(files.keys()) if _looks_like_test_file(path)]
    if not test_files:
        return []
    direct = [path for path in changed_paths if path in files and _looks_like_test_file(path)]
    if direct:
        return direct[:8]
    return test_files[:6]


async def _run_builder_targeted_tests(
    files: Dict[str, str],
    script_name: str,
    related_paths: List[str],
) -> Dict[str, Any]:
    from app.workers.tasks import _materialize_project_files, _run_subprocess

    npm_ci_timeout = int(os.getenv("APPS_BUILD_NPM_CI_TIMEOUT_SECONDS", "300"))
    test_timeout = int(os.getenv("APPS_BUILD_TEST_TIMEOUT_SECONDS", "240"))
    started_at = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="apps-builder-tests-") as temp_dir:
        project_dir = Path(temp_dir)
        _materialize_project_files(project_dir, files)

        has_lockfile = (project_dir / "package-lock.json").exists()
        install_command = ["npm", "ci"] if has_lockfile else ["npm", "install", "--no-audit", "--no-fund"]
        install_code, install_stdout, install_stderr = await _run_subprocess(
            install_command,
            cwd=project_dir,
            timeout_seconds=npm_ci_timeout,
        )
        if install_code != 0:
            install_name = "npm ci" if has_lockfile else "npm install"
            raise RuntimeError(
                f"`{install_name}` failed with exit code {install_code}\\n{install_stderr or install_stdout}"
            )

        command = ["npm", "run", script_name, "--", "--run", "--passWithNoTests"]
        if related_paths:
            command.extend(related_paths[:6])

        env = dict(os.environ)
        env["CI"] = "1"
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(project_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=test_timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            raise RuntimeError(f"Targeted tests timed out after {test_timeout}s (elapsed {elapsed_ms}ms)")

        return {
            "code": process.returncode or 0,
            "elapsed_ms": int((time.monotonic() - started_at) * 1000),
            "command": command,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }


async def _builder_tool_run_targeted_tests(files: Dict[str, str], changed_paths: List[str]) -> Dict[str, Any]:
    if not _builder_targeted_tests_enabled():
        return {
            "ok": True,
            "status": "skipped",
            "message": "targeted tests disabled (`APPS_BUILDER_TARGETED_TESTS_ENABLED=0`)",
            "changed_paths": changed_paths[:6],
        }

    script_name = _select_test_script(files)
    if not script_name:
        return {
            "ok": True,
            "status": "skipped",
            "message": "No test script found in package.json",
            "changed_paths": changed_paths[:6],
        }

    related_paths = _test_related_paths(files, changed_paths)
    if not related_paths:
        return {
            "ok": True,
            "status": "skipped",
            "message": "No test files detected in draft project",
            "changed_paths": changed_paths[:6],
        }

    try:
        result = await _run_builder_targeted_tests(files, script_name, related_paths)
    except Exception as exc:
        message = str(exc).strip() or "targeted test execution failed"
        if len(message) > 4000:
            message = message[:4000] + "... [truncated]"
        return {
            "ok": False,
            "status": "failed",
            "message": message,
            "changed_paths": changed_paths[:6],
            "test_paths": related_paths,
            "diagnostics": [{"message": message}],
        }

    code = int(result.get("code") or 0)
    if code != 0:
        output = str(result.get("stderr") or result.get("stdout") or "").strip()
        message = output or f"targeted tests failed with exit code {code}"
        if len(message) > 4000:
            message = message[:4000] + "... [truncated]"
        return {
            "ok": False,
            "status": "failed",
            "message": message,
            "changed_paths": changed_paths[:6],
            "test_paths": related_paths,
            "command": result.get("command"),
            "elapsed_ms": result.get("elapsed_ms"),
            "diagnostics": [{"message": message}],
        }

    return {
        "ok": True,
        "status": "passed",
        "message": "targeted tests passed",
        "changed_paths": changed_paths[:6],
        "test_paths": related_paths,
        "command": result.get("command"),
        "elapsed_ms": result.get("elapsed_ms"),
    }

async def _builder_tool_build_project_worker(files: Dict[str, str]) -> Dict[str, Any]:
    if not _builder_worker_build_gate_enabled():
        return {
            "ok": True,
            "status": "skipped",
            "message": "worker build tool disabled (`APPS_BUILDER_WORKER_BUILD_GATE_ENABLED=0`)",
        }
    try:
        dist_manifest = await _run_worker_build_preflight(files, include_dist_manifest=True)
    except Exception as exc:
        message = str(exc).strip() or "worker build failed"
        if len(message) > 4000:
            message = message[:4000] + "... [truncated]"
        return {
            "ok": False,
            "status": "failed",
            "message": message,
            "diagnostics": [{"message": message}],
        }
    if not isinstance(dist_manifest, dict):
        return {
            "ok": False,
            "status": "failed",
            "message": "worker build did not produce a dist manifest",
            "diagnostics": [{"message": "worker build did not produce a dist manifest"}],
        }
    return {
        "ok": True,
        "status": "succeeded",
        "dist_manifest": dist_manifest,
        "summary": _summarize_dist_manifest(dist_manifest),
    }


def _builder_tool_prepare_static_bundle(worker_build_result: Dict[str, Any]) -> Dict[str, Any]:
    status = str(worker_build_result.get("status") or "")
    if status == "skipped":
        return {
            "ok": True,
            "status": "skipped",
            "message": "worker build was skipped; static bundle preparation skipped",
        }
    if not worker_build_result.get("ok"):
        message = str(worker_build_result.get("message") or "worker build failed")
        diagnostics = worker_build_result.get("diagnostics")
        return {
            "ok": False,
            "status": "failed",
            "message": message,
            "diagnostics": diagnostics if isinstance(diagnostics, list) else [{"message": message}],
        }

    manifest = worker_build_result.get("dist_manifest")
    if not isinstance(manifest, dict):
        return {
            "ok": False,
            "status": "failed",
            "message": "dist manifest is missing for static bundle preparation",
            "diagnostics": [{"message": "dist manifest is missing for static bundle preparation"}],
        }
    return {
        "ok": True,
        "status": "ready",
        "message": "static bundle manifest prepared",
        "summary": _summarize_dist_manifest(manifest),
    }


def _collect_changed_paths(operations: List[BuilderPatchOp]) -> List[str]:
    changed: List[str] = []
    for op in operations:
        if op.path:
            changed.append(op.path)
        if op.from_path:
            changed.append(op.from_path)
        if op.to_path:
            changed.append(op.to_path)
    deduped: List[str] = []
    for path in changed:
        if path and path not in deduped:
            deduped.append(path)
    return deduped


async def _apply_patch_operations_to_sandbox(
    runtime_service: PublishedAppDraftDevRuntimeService,
    *,
    sandbox_id: str,
    operations: List[BuilderPatchOp],
) -> None:
    for op in operations:
        if op.op == "upsert_file" and op.path:
            await runtime_service.client.write_file(
                sandbox_id=sandbox_id,
                path=op.path,
                content=op.content or "",
            )
        elif op.op == "delete_file" and op.path:
            await runtime_service.client.delete_file(
                sandbox_id=sandbox_id,
                path=op.path,
            )
        elif op.op == "rename_file" and op.from_path and op.to_path:
            await runtime_service.client.rename_file(
                sandbox_id=sandbox_id,
                from_path=op.from_path,
                to_path=op.to_path,
            )


async def _snapshot_files_from_sandbox(
    runtime_service: PublishedAppDraftDevRuntimeService,
    *,
    sandbox_id: str,
) -> Dict[str, str]:
    payload = await runtime_service.client.snapshot_files(sandbox_id=sandbox_id)
    files = payload.get("files")
    if not isinstance(files, dict):
        raise RuntimeError("Sandbox snapshot did not return a files map")
    normalized: Dict[str, str] = {}
    for path, content in files.items():
        if isinstance(path, str):
            normalized[path] = content if isinstance(content, str) else str(content)
    return normalized


async def _run_allowlisted_sandbox_command(
    runtime_service: PublishedAppDraftDevRuntimeService,
    *,
    sandbox_id: str,
    command: List[str],
) -> Dict[str, Any]:
    allowlist = _builder_chat_command_allowlist()
    if not _is_allowed_sandbox_command(command, allowlist=allowlist):
        return {
            "ok": False,
            "status": "failed",
            "message": f"Sandbox command is not allowed: {' '.join(command)}",
            "diagnostics": [{"message": "Command not allowlisted"}],
        }
    result = await runtime_service.client.run_command(
        sandbox_id=sandbox_id,
        command=command,
        timeout_seconds=BUILDER_CHAT_COMMAND_TIMEOUT_SECONDS,
        max_output_bytes=BUILDER_CHAT_MAX_COMMAND_OUTPUT_BYTES,
    )
    code = int(result.get("code") or 0)
    if code != 0:
        message = str(result.get("stderr") or result.get("stdout") or "").strip()
        return {
            "ok": False,
            "status": "failed",
            "message": message or f"Command failed with exit code {code}",
            "diagnostics": [{"message": message or f"Command failed with exit code {code}"}],
            "command": command,
            "code": code,
            "stdout": result.get("stdout"),
            "stderr": result.get("stderr"),
        }
    return {
        "ok": True,
        "status": "passed",
        "message": "command passed",
        "command": command,
        "code": code,
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
    }


async def _create_draft_revision_from_files(
    db: AsyncSession,
    *,
    app: PublishedApp,
    current: PublishedAppRevision,
    actor_id: Optional[UUID],
    files: Dict[str, str],
    entry_file: str,
) -> PublishedAppRevision:
    _validate_builder_project_or_raise(files, entry_file)
    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=entry_file,
        files=files,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=_next_build_seq(current),
        build_error=None,
        build_started_at=None,
        build_finished_at=None,
        dist_storage_prefix=None,
        dist_manifest=None,
        template_runtime="vite_static",
        compiled_bundle=None,
        bundle_hash=sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
        source_revision_id=current.id,
        created_by=actor_id,
    )
    db.add(revision)
    await db.flush()
    app.current_draft_revision_id = revision.id
    return revision


async def _run_builder_agentic_loop(
    *,
    user_prompt: str,
    files: Dict[str, str],
    entry_file: str,
    request_id: str,
    runtime_service: Optional[PublishedAppDraftDevRuntimeService] = None,
    sandbox_id: Optional[str] = None,
) -> tuple[BuilderPatchGenerationResult, List[Dict[str, Any]], Dict[str, str], str]:
    def tool_started(stage: str, tool: str, iteration: int, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload_data: Dict[str, Any] = {"tool": tool, "iteration": iteration}
        if isinstance(data, dict):
            payload_data.update(data)
        return _stream_event_payload(
            event="tool_started",
            stage=stage,
            request_id=request_id,
            data=payload_data,
        )

    def tool_finished(
        *,
        stage: str,
        tool: str,
        iteration: int,
        ok: bool,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return _stream_event_payload(
            event="tool_completed" if ok else "tool_failed",
            stage=stage,
            request_id=request_id,
            data={
                "tool": tool,
                "iteration": iteration,
                "status": "ok" if ok else "failed",
                "result": result,
            },
            diagnostics=result.get("diagnostics") if not ok else None,
        )

    trace_events: List[Dict[str, Any]] = []
    repair_feedback: List[str] = []
    recent_paths: List[str] = []
    aggregate_ops: List[BuilderPatchOp] = []
    working_files = dict(files)
    working_entry = entry_file
    focus_paths = _extract_prompt_focus_paths(working_files, user_prompt, max_paths=4)

    for iteration in range(1, BUILDER_AGENT_MAX_ITERATIONS + 1):
        trace_events.append(tool_started("inspect", "list_files", iteration))
        list_result = _builder_tool_list_files(working_files)
        trace_events.append(tool_finished(stage="inspect", tool="list_files", iteration=iteration, ok=True, result=list_result))
        inspect_paths: List[str] = []
        for path in focus_paths:
            if path in working_files and path not in inspect_paths:
                inspect_paths.append(path)
        if recent_paths:
            recent_candidate = recent_paths[-1]
            if recent_candidate in working_files and recent_candidate not in inspect_paths:
                inspect_paths.append(recent_candidate)
        for inspect_path in inspect_paths[:3]:
            trace_events.append(tool_started("inspect", "read_file", iteration, {"path": inspect_path}))
            read_result = _builder_tool_read_file(working_files, inspect_path)
            trace_events.append(tool_finished(stage="inspect", tool="read_file", iteration=iteration, ok=True, result=read_result))
        trace_events.append(tool_started("inspect", "search_code", iteration))
        search_result = _builder_tool_search_code(working_files, user_prompt)
        trace_events.append(tool_finished(stage="inspect", tool="search_code", iteration=iteration, ok=True, result=search_result))

        model_recent_paths: List[str] = []
        for path in focus_paths + recent_paths:
            if path and path not in model_recent_paths:
                model_recent_paths.append(path)
        model_recent_paths = model_recent_paths[:8]

        result = await _generate_builder_patch_with_model(
            user_prompt=user_prompt,
            files=working_files,
            entry_file=working_entry,
            repair_feedback=repair_feedback,
            recent_paths=model_recent_paths,
        )

        dry_run_result = _builder_tool_apply_patch_dry_run(
            working_files,
            working_entry,
            result.operations,
        )
        trace_events.append(tool_started("patch_dry_run", "apply_patch_dry_run", iteration))
        trace_events.append(
            tool_finished(
                stage="patch_dry_run",
                tool="apply_patch_dry_run",
                iteration=iteration,
                ok=bool(dry_run_result.get("ok")),
                result=dry_run_result,
            )
        )
        if not dry_run_result.get("ok"):
            failure_message = str(dry_run_result.get("message") or "patch dry run failed")
            repair_feedback.append(failure_message)
            continue

        working_files, working_entry = _apply_patch_operations(
            working_files,
            working_entry,
            result.operations,
        )
        aggregate_ops.extend(result.operations)
        recent_paths = [
            op.path
            for op in result.operations
            if op.path
        ] + [
            op.to_path
            for op in result.operations
            if op.to_path
        ]
        recent_paths = [path for path in recent_paths if path][:8]
        focus_paths = _extract_prompt_focus_paths(working_files, user_prompt, max_paths=4)
        if runtime_service is not None and sandbox_id:
            try:
                trace_events.append(tool_started("edit", "apply_sandbox_patch", iteration))
                await _apply_patch_operations_to_sandbox(
                    runtime_service,
                    sandbox_id=sandbox_id,
                    operations=result.operations,
                )
                trace_events.append(
                    tool_finished(
                        stage="edit",
                        tool="apply_sandbox_patch",
                        iteration=iteration,
                        ok=True,
                        result={
                            "status": "applied",
                            "changed_paths": _collect_changed_paths(result.operations),
                        },
                    )
                )
            except Exception as exc:
                failed = {
                    "status": "failed",
                    "message": str(exc),
                    "diagnostics": [{"message": str(exc)}],
                }
                trace_events.append(
                    tool_finished(
                        stage="edit",
                        tool="apply_sandbox_patch",
                        iteration=iteration,
                        ok=False,
                        result=failed,
                    )
                )
                repair_feedback.append(str(exc))
                continue

        compile_result = _builder_tool_compile_project(working_files, working_entry)
        trace_events.append(tool_started("compile", "compile_project", iteration))
        trace_events.append(
            tool_finished(
                stage="compile",
                tool="compile_project",
                iteration=iteration,
                ok=bool(compile_result.get("ok")),
                result=compile_result,
            )
        )
        if not compile_result.get("ok"):
            repair_feedback.append(str(compile_result.get("message") or "compile failed"))
            continue

        test_result = await _builder_tool_run_targeted_tests(working_files, recent_paths)
        trace_events.append(tool_started("test", "run_targeted_tests", iteration))
        trace_events.append(
            tool_finished(
                stage="test",
                tool="run_targeted_tests",
                iteration=iteration,
                ok=bool(test_result.get("ok")),
                result=test_result,
            )
        )
        if not test_result.get("ok"):
            repair_feedback.append(str(test_result.get("message") or "targeted tests failed"))
            continue

        if _builder_chat_commands_enabled() and runtime_service is not None and sandbox_id:
            trace_events.append(tool_started("command", "run_command", iteration, {"command": "npm run build"}))
            build_command_result = await _run_allowlisted_sandbox_command(
                runtime_service,
                sandbox_id=sandbox_id,
                command=["npm", "run", "build"],
            )
            trace_events.append(
                tool_finished(
                    stage="command",
                    tool="run_command",
                    iteration=iteration,
                    ok=bool(build_command_result.get("ok")),
                    result=build_command_result,
                )
            )
            if not build_command_result.get("ok"):
                repair_feedback.append(str(build_command_result.get("message") or "sandbox build failed"))
                continue
        elif _builder_chat_worker_precheck_enabled():
            worker_build_result = await _builder_tool_build_project_worker(working_files)
            trace_events.append(tool_started("worker_build", "build_project_worker", iteration))
            trace_events.append(
                tool_finished(
                    stage="worker_build",
                    tool="build_project_worker",
                    iteration=iteration,
                    ok=bool(worker_build_result.get("ok")),
                    result=worker_build_result,
                )
            )
            if not worker_build_result.get("ok"):
                repair_feedback.append(str(worker_build_result.get("message") or "worker build failed"))
                continue

        return (
            BuilderPatchGenerationResult(
                operations=aggregate_ops,
                summary=result.summary,
                rationale=result.rationale,
                assumptions=result.assumptions,
            ),
            trace_events,
            working_files,
            working_entry,
        )

    exc = _builder_compile_error(
        "Agentic loop could not produce a valid patch",
        diagnostics=[{"message": item} for item in repair_feedback[-6:]] or [{"message": "No valid patch generated"}],
    )
    setattr(exc, "builder_trace_events", list(trace_events))
    raise exc


def _normalize_builder_path(path: str) -> str:
    raw = (path or "").replace("\\", "/").strip()
    if not raw:
        raise _builder_policy_error("File path is required", field="path")
    if raw.startswith("/"):
        raise _builder_policy_error("Absolute paths are not allowed", field="path")

    parts: List[str] = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise _builder_policy_error("Path traversal is not allowed", field="path")
        parts.append(part)
    normalized = "/".join(parts)
    if not normalized:
        raise _builder_policy_error("File path is required", field="path")
    return normalized


def _assert_builder_path_allowed(path: str, *, field: str = "path") -> None:
    in_allowed_dir = any(path.startswith(root) for root in BUILDER_ALLOWED_DIR_ROOTS)
    if not in_allowed_dir:
        is_root_file = "/" not in path
        matches_root_file = path in BUILDER_ALLOWED_ROOT_FILES
        matches_root_glob = any(PurePosixPath(path).match(pattern) for pattern in BUILDER_ALLOWED_ROOT_GLOBS)
        if not (is_root_file and (matches_root_file or matches_root_glob)):
            raise _builder_policy_error(
                "File path must be in src/, public/, or an allowed Vite root file",
                field=field,
            )

    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in BUILDER_ALLOWED_EXTENSIONS:
        raise _builder_policy_error(
            f"Unsupported file extension: {suffix or '(none)'}",
            field=field,
        )


def _resolve_local_project_import(import_path: str, importer_path: str, files: Dict[str, str]) -> Optional[str]:
    importer_dir = PurePosixPath(importer_path).parent.as_posix()
    joined = PurePosixPath(importer_dir, import_path).as_posix()
    parts: List[str] = []
    for part in joined.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    normalized = "/".join(parts)
    if not normalized:
        return None
    candidates = [
        normalized,
        f"{normalized}.tsx",
        f"{normalized}.ts",
        f"{normalized}.mts",
        f"{normalized}.cts",
        f"{normalized}.jsx",
        f"{normalized}.js",
        f"{normalized}.css",
        f"{normalized}/index.tsx",
        f"{normalized}/index.ts",
        f"{normalized}/index.mts",
        f"{normalized}/index.cts",
        f"{normalized}/index.jsx",
        f"{normalized}/index.js",
    ]
    for candidate in candidates:
        if candidate in files:
            return candidate
    return None


def _validate_builder_project_or_raise(files: Dict[str, str], entry_file: str) -> List[Dict[str, str]]:
    diagnostics: List[Dict[str, str]] = []

    if entry_file not in files:
        raise _builder_compile_error(
            "Entry file does not exist in project",
            diagnostics=[{"path": entry_file, "message": "Entry file is missing"}],
        )

    if len(files) > BUILDER_MAX_FILES:
        raise _builder_policy_error(
            f"Too many files in draft (limit: {BUILDER_MAX_FILES})",
            field="files",
        )

    total_size = 0
    for path, content in files.items():
        _assert_builder_path_allowed(path, field="files")
        encoded_size = len(content.encode("utf-8"))
        max_bytes = BUILDER_MAX_LOCKFILE_BYTES if path in BUILDER_LOCKFILE_NAMES else BUILDER_MAX_FILE_BYTES
        if encoded_size > max_bytes:
            raise _builder_policy_error(
                f"File exceeds size limit ({max_bytes} bytes): {path}",
                field="files",
            )
        total_size += encoded_size
    if total_size > BUILDER_MAX_PROJECT_BYTES:
        raise _builder_policy_error(
            f"Project exceeds size limit ({BUILDER_MAX_PROJECT_BYTES} bytes)",
            field="files",
        )

    code_files = [
        path for path in files.keys()
        if PurePosixPath(path).suffix.lower() in {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
    ]
    for path in code_files:
        source = files.get(path, "")
        for match in IMPORT_RE.findall(source):
            spec = match.strip()
            if not spec:
                continue
            if spec.startswith("."):
                if _resolve_local_project_import(spec, path, files) is None:
                    diagnostics.append({"path": path, "message": f"Unresolved local import: {spec}"})

    diagnostics.extend(validate_builder_dependency_policy(files))

    if diagnostics:
        raise _builder_compile_error("Project validation failed", diagnostics=diagnostics)
    return diagnostics


def _coerce_files_payload(files: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for raw_path, raw_content in files.items():
        path = _normalize_builder_path(raw_path)
        _assert_builder_path_allowed(path, field="files")
        content = raw_content if isinstance(raw_content, str) else json.dumps(raw_content)
        normalized[path] = content
    return normalized


def _apply_patch_operations(
    files: Dict[str, str],
    entry_file: str,
    operations: List[BuilderPatchOp],
) -> tuple[Dict[str, str], str]:
    if len(operations) > BUILDER_MAX_OPS:
        raise _builder_policy_error(
            f"Too many patch operations (limit: {BUILDER_MAX_OPS})",
            field="operations",
        )

    next_files = dict(files)
    next_entry = _normalize_builder_path(entry_file)
    _assert_builder_path_allowed(next_entry, field="entry_file")
    for operation in operations:
        if operation.op == "upsert_file":
            if not operation.path:
                raise _builder_policy_error("upsert_file requires path", field="operations.path")
            normalized_path = _normalize_builder_path(operation.path)
            _assert_builder_path_allowed(normalized_path, field="operations.path")
            next_files[normalized_path] = operation.content or ""
        elif operation.op == "delete_file":
            if not operation.path:
                raise _builder_policy_error("delete_file requires path", field="operations.path")
            normalized_path = _normalize_builder_path(operation.path)
            _assert_builder_path_allowed(normalized_path, field="operations.path")
            next_files.pop(normalized_path, None)
            if next_entry == normalized_path:
                next_entry = "src/main.tsx"
        elif operation.op == "rename_file":
            if not operation.from_path or not operation.to_path:
                raise _builder_policy_error(
                    "rename_file requires from_path and to_path",
                    field="operations.path",
                )
            from_path = _normalize_builder_path(operation.from_path)
            to_path = _normalize_builder_path(operation.to_path)
            _assert_builder_path_allowed(from_path, field="operations.from_path")
            _assert_builder_path_allowed(to_path, field="operations.to_path")
            if from_path not in next_files:
                raise _builder_policy_error(
                    f"rename_file source does not exist: {from_path}",
                    field="operations.from_path",
                )
            if to_path in next_files and to_path != from_path:
                raise _builder_policy_error(
                    f"rename_file target already exists: {to_path}",
                    field="operations.to_path",
                )
            next_files[to_path] = next_files.pop(from_path)
            if next_entry == from_path:
                next_entry = to_path
        elif operation.op == "set_entry_file":
            if not operation.entry_file:
                raise _builder_policy_error("set_entry_file requires entry_file", field="operations.entry_file")
            next_entry = _normalize_builder_path(operation.entry_file)
            _assert_builder_path_allowed(next_entry, field="operations.entry_file")

    if next_entry not in next_files:
        raise _builder_policy_error("entry_file must exist in files", field="entry_file")
    _validate_builder_project_or_raise(next_files, next_entry)
    return next_files, next_entry


def _sanitize_prompt_text(text: str, limit: int = 120) -> str:
    collapsed = " ".join(text.strip().split())
    if not collapsed:
        return ""
    return collapsed[:limit]


def _build_builder_patch_from_prompt(
    user_prompt: str,
    files: Dict[str, str],
) -> tuple[List[Dict[str, str]], str]:
    prompt = _sanitize_prompt_text(user_prompt, 140)
    prompt_lower = prompt.lower()
    patch_ops: List[Dict[str, str]] = []
    applied: List[str] = []

    app_source = files.get("src/App.tsx")
    if app_source is not None:
        updated_app = app_source

        if "Start a conversation." in updated_app:
            next_copy = f"Start a conversation. ({prompt})"
            next_app = updated_app.replace("Start a conversation.", next_copy, 1)
            if next_app != updated_app:
                updated_app = next_app
                applied.append("updated empty-state copy")

        if ("title" in prompt_lower or "rename" in prompt_lower or "name" in prompt_lower) and "const title = useMemo(() =>" in updated_app:
            title_text = prompt[:48].replace("\"", "'")
            next_app = re.sub(
                r'const title = useMemo\(\(\) => ".*?", \[\]\);',
                f'const title = useMemo(() => "{title_text}", []);',
                updated_app,
                count=1,
            )
            if next_app != updated_app:
                updated_app = next_app
                applied.append("updated app title")

        if "bold" in prompt_lower and "fontWeight: 700" not in updated_app:
            next_app = updated_app.replace(
                "fontSize: 16, fontFamily: theme.fontDisplay",
                "fontSize: 16, fontFamily: theme.fontDisplay, fontWeight: 700",
                1,
            )
            if next_app != updated_app:
                updated_app = next_app
                applied.append("made header title bold")

        if updated_app != app_source:
            patch_ops.append({"op": "upsert_file", "path": "src/App.tsx", "content": updated_app})

    theme_source = files.get("src/theme.ts")
    if theme_source is not None:
        color_map = {
            "blue": "#2563eb",
            "green": "#16a34a",
            "red": "#dc2626",
            "orange": "#ea580c",
            "teal": "#0f766e",
            "purple": "#7c3aed",
        }
        selected_color = next((hex_value for name, hex_value in color_map.items() if name in prompt_lower), None)
        if selected_color:
            next_theme = re.sub(
                r'accent:\s*".*?"',
                f'accent: "{selected_color}"',
                theme_source,
                count=1,
            )
            if next_theme != theme_source:
                patch_ops.append({"op": "upsert_file", "path": "src/theme.ts", "content": next_theme})
                applied.append(f"set accent color to {selected_color}")

    if not patch_ops and app_source is not None:
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        fallback_text = f"Start a conversation. ({prompt} · {timestamp})"
        next_app = app_source.replace("Start a conversation.", fallback_text, 1)
        if next_app == app_source:
            next_app = app_source.rstrip() + f"\n// Builder note: {prompt} ({timestamp})\n"
        patch_ops.append({"op": "upsert_file", "path": "src/App.tsx", "content": next_app})
        applied.append("applied fallback draft edit")

    summary = ", ".join(dict.fromkeys(applied)) if applied else "prepared a draft update"
    return patch_ops, summary


@router.get("", response_model=List[PublishedAppResponse])
async def list_published_apps(
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    result = await db.execute(
        select(PublishedApp)
        .where(PublishedApp.tenant_id == ctx["tenant_id"])
        .order_by(PublishedApp.updated_at.desc())
    )
    return [_app_to_response(app) for app in result.scalars().all()]


@router.get("/templates", response_model=List[PublishedAppTemplateResponse])
async def list_published_app_templates(
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
):
    return [_template_to_response(template) for template in list_templates()]


@router.post("", response_model=PublishedAppResponse)
async def create_published_app(
    payload: CreatePublishedAppRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    template_key = _validate_template_key(payload.template_key)
    candidate_slug = (payload.slug or "").strip().lower()
    if candidate_slug:
        if not APP_SLUG_PATTERN.match(candidate_slug):
            raise HTTPException(status_code=400, detail="Slug must be lowercase, 3-64 chars, and contain only letters, numbers, hyphens")
        slug = await _generate_unique_slug(db, candidate_slug)
    else:
        slug = await _generate_unique_slug(db, payload.name)

    providers = _validate_providers(payload.auth_providers)
    await _validate_agent(db, ctx["tenant_id"], payload.agent_id)

    app = PublishedApp(
        tenant_id=ctx["tenant_id"],
        agent_id=payload.agent_id,
        name=payload.name.strip(),
        slug=slug,
        template_key=template_key,
        auth_enabled=payload.auth_enabled,
        auth_providers=providers,
        created_by=ctx["user"].id if ctx["user"] else None,
        status=PublishedAppStatus.draft,
    )
    db.add(app)
    try:
        await db.flush()

        template = get_template(template_key)
        files = build_template_files(template_key)
        revision = PublishedAppRevision(
            published_app_id=app.id,
            kind=PublishedAppRevisionKind.draft,
            template_key=template_key,
            entry_file=template.entry_file,
            files=files,
            build_status=PublishedAppRevisionBuildStatus.queued,
            build_seq=1,
            build_error=None,
            build_started_at=None,
            build_finished_at=None,
            dist_storage_prefix=None,
            dist_manifest=None,
            template_runtime="vite_static",
            compiled_bundle=None,
            bundle_hash=sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
            source_revision_id=None,
            created_by=ctx["user"].id if ctx["user"] else None,
        )
        db.add(revision)
        await db.flush()
        app.current_draft_revision_id = revision.id

        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Published app slug or name already exists")

    await db.refresh(app)
    return _app_to_response(app)


@router.get("/{app_id}", response_model=PublishedAppResponse)
async def get_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    return _app_to_response(app)


@router.get("/{app_id}/builder/state", response_model=BuilderStateResponse)
async def get_builder_state(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor_id = ctx["user"].id if ctx["user"] else None

    draft = await _ensure_current_draft_revision(db, app, actor_id)
    published = await _get_revision(db, app.current_published_revision_id)
    draft_dev_session: Optional[PublishedAppDraftDevSession] = None
    if actor_id:
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        await runtime_service.expire_idle_sessions(app_id=app.id, user_id=actor_id)
        draft_dev_session = await _get_draft_dev_session_for_scope(
            db,
            app_id=app.id,
            user_id=actor_id,
        )
    await db.commit()
    await db.refresh(app)

    preview_token: Optional[str] = None
    if actor_id and draft:
        preview_token = create_published_app_preview_token(
            subject=str(actor_id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            revision_id=str(draft.id),
            scopes=["apps.preview"],
        )

    return BuilderStateResponse(
        app=_app_to_response(app),
        templates=[_template_to_response(template) for template in list_templates()],
        current_draft_revision=_revision_to_response(draft) if draft else None,
        current_published_revision=_revision_to_response(published) if published else None,
        preview_token=preview_token,
        draft_dev=_draft_dev_session_to_response(draft_dev_session) if draft_dev_session else None,
    )


@router.post("/{app_id}/builder/revisions", response_model=PublishedAppRevisionResponse)
async def create_builder_revision(
    app_id: UUID,
    payload: CreateBuilderRevisionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor_id = ctx["user"].id if ctx["user"] else None
    current = await _ensure_current_draft_revision(db, app, actor_id)

    if payload.base_revision_id and str(payload.base_revision_id) != str(current.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(current.id),
                "latest_updated_at": current.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )

    if payload.files is not None:
        next_files = _coerce_files_payload(payload.files)
        next_entry = _normalize_builder_path(payload.entry_file or current.entry_file)
        _assert_builder_path_allowed(next_entry, field="entry_file")
        _validate_builder_project_or_raise(next_files, next_entry)
    else:
        next_files, next_entry = _apply_patch_operations(
            dict(current.files or {}),
            payload.entry_file or current.entry_file,
            payload.operations,
        )

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file=next_entry,
        files=next_files,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=_next_build_seq(current),
        build_error=None,
        build_started_at=None,
        build_finished_at=None,
        dist_storage_prefix=None,
        dist_manifest=None,
        template_runtime="vite_static",
        compiled_bundle=None,
        bundle_hash=sha256(json.dumps(next_files, sort_keys=True).encode("utf-8")).hexdigest(),
        source_revision_id=current.id,
        created_by=actor_id,
    )
    db.add(revision)
    await db.flush()

    app.current_draft_revision_id = revision.id
    await db.commit()
    await db.refresh(app)
    await db.refresh(revision)
    return _revision_to_response(revision)


@router.get(
    "/{app_id}/builder/draft-dev/session",
    response_model=DraftDevSessionResponse,
)
async def get_builder_draft_dev_session(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    await runtime_service.expire_idle_sessions(app_id=app.id, user_id=actor.id)
    session = await _get_draft_dev_session_for_scope(
        db,
        app_id=app.id,
        user_id=actor.id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")
    await db.commit()
    return _draft_dev_session_to_response(session)


@router.post(
    "/{app_id}/builder/draft-dev/session/ensure",
    response_model=DraftDevSessionResponse,
)
async def ensure_builder_draft_dev_session(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    draft = await _ensure_current_draft_revision(db, app, actor.id)
    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        session = await runtime_service.ensure_session(
            app=app,
            revision=draft,
            user_id=actor.id,
        )
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    return _draft_dev_session_to_response(session)


@router.patch(
    "/{app_id}/builder/draft-dev/session/sync",
    response_model=DraftDevSessionResponse,
)
async def sync_builder_draft_dev_session(
    app_id: UUID,
    payload: DraftDevSyncRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    draft = await _ensure_current_draft_revision(db, app, actor.id)
    files = _coerce_files_payload(payload.files)
    entry_file = _normalize_builder_path(payload.entry_file or draft.entry_file)
    _assert_builder_path_allowed(entry_file, field="entry_file")
    _validate_builder_project_or_raise(files, entry_file)

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        session = await runtime_service.sync_session(
            app=app,
            revision=draft,
            user_id=actor.id,
            files=files,
            entry_file=entry_file,
        )
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    await db.commit()
    return _draft_dev_session_to_response(session)


@router.post(
    "/{app_id}/builder/draft-dev/session/heartbeat",
    response_model=DraftDevSessionResponse,
)
async def heartbeat_builder_draft_dev_session(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    session = await _get_draft_dev_session_for_scope(db, app_id=app.id, user_id=actor.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    try:
        session = await runtime_service.heartbeat_session(session=session)
    except PublishedAppDraftDevRuntimeDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    return _draft_dev_session_to_response(session)


@router.delete(
    "/{app_id}/builder/draft-dev/session",
    response_model=DraftDevSessionResponse,
)
async def delete_builder_draft_dev_session(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    actor = ctx.get("user")
    if actor is None:
        raise HTTPException(status_code=403, detail="Draft dev session requires a user principal")
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    session = await _get_draft_dev_session_for_scope(db, app_id=app.id, user_id=actor.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Draft dev session not found")

    runtime_service = PublishedAppDraftDevRuntimeService(db)
    await runtime_service.stop_session(
        session=session,
        reason=PublishedAppDraftDevSessionStatus.stopped,
    )
    await db.commit()
    return _draft_dev_session_to_response(session)


@router.get(
    "/{app_id}/builder/revisions/{revision_id}/build",
    response_model=RevisionBuildStatusResponse,
)
async def get_builder_revision_build_status(
    app_id: UUID,
    revision_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    revision = await _get_revision_for_app(db, app.id, revision_id)
    return _revision_build_status_to_response(revision)


@router.post(
    "/{app_id}/builder/revisions/{revision_id}/build/retry",
    response_model=RevisionBuildStatusResponse,
)
async def retry_builder_revision_build(
    app_id: UUID,
    revision_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    revision = await _get_revision_for_app(db, app.id, revision_id)

    revision.build_status = PublishedAppRevisionBuildStatus.queued
    revision.build_seq = int(revision.build_seq or 0) + 1
    revision.build_error = None
    revision.build_started_at = None
    revision.build_finished_at = None
    revision.dist_storage_prefix = None
    revision.dist_manifest = None
    revision.template_runtime = revision.template_runtime or "vite_static"
    enqueue_error = _enqueue_revision_build(
        revision=revision,
        app=app,
        build_kind=revision.kind.value if hasattr(revision.kind, "value") else str(revision.kind),
    )
    if enqueue_error:
        _mark_revision_build_enqueue_failed(revision=revision, reason=enqueue_error)
    await db.commit()
    await db.refresh(revision)
    return _revision_build_status_to_response(revision)


@router.post("/{app_id}/builder/validate", response_model=BuilderValidationResponse)
async def validate_builder_revision(
    app_id: UUID,
    payload: CreateBuilderRevisionRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor_id = ctx["user"].id if ctx["user"] else None
    current = await _ensure_current_draft_revision(db, app, actor_id)

    if payload.base_revision_id and str(payload.base_revision_id) != str(current.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(current.id),
                "latest_updated_at": current.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )

    if payload.files is not None:
        next_files = _coerce_files_payload(payload.files)
        next_entry = _normalize_builder_path(payload.entry_file or current.entry_file)
        _assert_builder_path_allowed(next_entry, field="entry_file")
    else:
        next_files, next_entry = _apply_patch_operations(
            dict(current.files or {}),
            payload.entry_file or current.entry_file,
            payload.operations,
        )

    diagnostics = _validate_builder_project_or_raise(next_files, next_entry)
    return BuilderValidationResponse(
        ok=True,
        entry_file=next_entry,
        file_count=len(next_files),
        diagnostics=diagnostics,
    )


@router.post("/{app_id}/builder/template-reset", response_model=PublishedAppRevisionResponse)
async def reset_builder_template(
    app_id: UUID,
    payload: TemplateResetRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor_id = ctx["user"].id if ctx["user"] else None
    current = await _ensure_current_draft_revision(db, app, actor_id)

    template_key = _validate_template_key(payload.template_key)
    template = get_template(template_key)
    files = build_template_files(template_key)
    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=template_key,
        entry_file=template.entry_file,
        files=files,
        build_status=PublishedAppRevisionBuildStatus.queued,
        build_seq=_next_build_seq(current),
        build_error=None,
        build_started_at=None,
        build_finished_at=None,
        dist_storage_prefix=None,
        dist_manifest=None,
        template_runtime="vite_static",
        compiled_bundle=None,
        bundle_hash=sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest(),
        source_revision_id=current.id,
        created_by=actor_id,
    )
    db.add(revision)
    await db.flush()

    app.template_key = template_key
    app.current_draft_revision_id = revision.id

    await db.commit()
    await db.refresh(revision)
    return _revision_to_response(revision)


@router.get("/{app_id}/builder/conversations", response_model=List[BuilderConversationTurnResponse])
async def list_builder_conversations(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)

    result = await db.execute(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == app.id)
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
        .limit(limit)
    )
    return [_builder_conversation_to_response(turn) for turn in result.scalars().all()]


@router.get("/{app_id}/builder/checkpoints", response_model=List[BuilderCheckpointResponse])
async def list_builder_checkpoints(
    app_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    fetch_limit = min(max(1, limit), BUILDER_CHECKPOINT_LIST_LIMIT)
    result = await db.execute(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == app.id)
        .where(PublishedAppBuilderConversationTurn.status == BuilderConversationTurnStatus.succeeded)
        .where(PublishedAppBuilderConversationTurn.result_revision_id.is_not(None))
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
        .limit(fetch_limit)
    )
    turns = result.scalars().all()
    checkpoints: List[BuilderCheckpointResponse] = []
    for turn in turns:
        if turn.result_revision_id:
            checkpoints.append(_builder_checkpoint_to_response(turn))
    return checkpoints


@router.post("/{app_id}/builder/undo", response_model=BuilderUndoResponse)
async def undo_builder_last_run(
    app_id: UUID,
    payload: BuilderUndoRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    current = await _ensure_current_draft_revision(db, app, actor_id)
    if payload.base_revision_id and str(payload.base_revision_id) != str(current.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(current.id),
                "latest_updated_at": current.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )

    turn_result = await db.execute(
        select(PublishedAppBuilderConversationTurn)
        .where(PublishedAppBuilderConversationTurn.published_app_id == app.id)
        .where(PublishedAppBuilderConversationTurn.status == BuilderConversationTurnStatus.succeeded)
        .where(PublishedAppBuilderConversationTurn.checkpoint_type == BuilderCheckpointType.auto_run)
        .where(PublishedAppBuilderConversationTurn.result_revision_id.is_not(None))
        .order_by(PublishedAppBuilderConversationTurn.created_at.desc())
        .limit(1)
    )
    checkpoint_turn = turn_result.scalar_one_or_none()
    if checkpoint_turn is None or checkpoint_turn.result_revision_id is None:
        raise HTTPException(status_code=404, detail="No automatic checkpoint found to undo")

    checkpoint_revision = await _get_revision_for_app(db, app.id, checkpoint_turn.result_revision_id)
    if checkpoint_revision.source_revision_id is None:
        raise HTTPException(status_code=409, detail="Checkpoint has no source revision to restore")
    restore_revision = await _get_revision_for_app(db, app.id, checkpoint_revision.source_revision_id)

    restored_files = dict(restore_revision.files or {})
    restored_entry = restore_revision.entry_file
    new_revision = await _create_draft_revision_from_files(
        db,
        app=app,
        current=current,
        actor_id=actor_id,
        files=restored_files,
        entry_file=restored_entry,
    )

    if actor and _builder_chat_sandbox_tools_enabled():
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        try:
            await runtime_service.sync_session(
                app=app,
                revision=new_revision,
                user_id=actor.id,
                files=restored_files,
                entry_file=restored_entry,
            )
        except PublishedAppDraftDevRuntimeDisabled:
            pass

    request_id = _new_builder_request_id()
    await _persist_builder_conversation_turn(
        db,
        app_id=app.id,
        revision_id=current.id,
        result_revision_id=new_revision.id,
        actor_id=actor_id,
        request_id=request_id,
        user_prompt="Undo last run",
        status=BuilderConversationTurnStatus.succeeded,
        trace_events=[],
        checkpoint_type=BuilderCheckpointType.undo,
        checkpoint_label=f"Undo to {restore_revision.id}",
    )
    await db.commit()
    await db.refresh(new_revision)
    return BuilderUndoResponse(
        revision=_revision_to_response(new_revision),
        restored_from_revision_id=str(restore_revision.id),
        checkpoint_turn_id=str(checkpoint_turn.id),
        request_id=request_id,
    )


@router.post("/{app_id}/builder/revert-file", response_model=BuilderRevertFileResponse)
async def revert_builder_file(
    app_id: UUID,
    payload: BuilderRevertFileRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    current = await _ensure_current_draft_revision(db, app, actor_id)
    if payload.base_revision_id and str(payload.base_revision_id) != str(current.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(current.id),
                "latest_updated_at": current.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )

    normalized_path = _normalize_builder_path(payload.path)
    _assert_builder_path_allowed(normalized_path, field="path")
    from_revision = await _get_revision_for_app(db, app.id, payload.from_revision_id)

    next_files = dict(current.files or {})
    if normalized_path in (from_revision.files or {}):
        next_files[normalized_path] = str((from_revision.files or {})[normalized_path])
    else:
        next_files.pop(normalized_path, None)

    next_entry = current.entry_file
    if normalized_path == current.entry_file and normalized_path not in next_files:
        raise HTTPException(status_code=409, detail="Cannot remove the current entry file")

    new_revision = await _create_draft_revision_from_files(
        db,
        app=app,
        current=current,
        actor_id=actor_id,
        files=next_files,
        entry_file=next_entry,
    )

    if actor and _builder_chat_sandbox_tools_enabled():
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        try:
            await runtime_service.sync_session(
                app=app,
                revision=new_revision,
                user_id=actor.id,
                files=next_files,
                entry_file=next_entry,
            )
        except PublishedAppDraftDevRuntimeDisabled:
            pass

    request_id = _new_builder_request_id()
    await _persist_builder_conversation_turn(
        db,
        app_id=app.id,
        revision_id=current.id,
        result_revision_id=new_revision.id,
        actor_id=actor_id,
        request_id=request_id,
        user_prompt=f"Revert file: {normalized_path}",
        status=BuilderConversationTurnStatus.succeeded,
        trace_events=[],
        checkpoint_type=BuilderCheckpointType.file_revert,
        checkpoint_label=f"Revert {normalized_path}",
    )
    await db.commit()
    await db.refresh(new_revision)
    return BuilderRevertFileResponse(
        revision=_revision_to_response(new_revision),
        reverted_path=normalized_path,
        from_revision_id=str(from_revision.id),
        request_id=request_id,
    )


@router.post("/{app_id}/builder/chat/stream")
async def builder_chat_stream(
    app_id: UUID,
    payload: BuilderChatRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    draft = await _ensure_current_draft_revision(db, app, actor_id)

    if payload.base_revision_id and str(payload.base_revision_id) != str(draft.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(draft.id),
                "latest_updated_at": draft.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )

    user_prompt = payload.input.strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="input is required")

    existing_files = dict(draft.files or {})
    request_id = _new_builder_request_id()
    trace_events: List[Dict[str, Any]] = []
    generation_result: Optional[BuilderPatchGenerationResult] = None
    patch_ops_payload: List[Dict[str, Any]] = []
    runtime_service: Optional[PublishedAppDraftDevRuntimeService] = None
    sandbox_id: Optional[str] = None
    final_files = dict(existing_files)
    final_entry = draft.entry_file
    saved_revision: Optional[PublishedAppRevision] = None
    try:
        if actor is not None and _builder_chat_sandbox_tools_enabled():
            runtime_service = PublishedAppDraftDevRuntimeService(db)
            try:
                session = await runtime_service.ensure_session(
                    app=app,
                    revision=draft,
                    user_id=actor.id,
                    files=existing_files,
                    entry_file=draft.entry_file,
                )
            except PublishedAppDraftDevRuntimeDisabled as exc:
                raise HTTPException(status_code=409, detail=str(exc))
            sandbox_id = session.sandbox_id
            if session.status == PublishedAppDraftDevSessionStatus.error:
                raise HTTPException(status_code=409, detail=session.last_error or "Draft dev sandbox failed to start")
            if not sandbox_id:
                raise HTTPException(status_code=409, detail="Draft dev sandbox id is missing")
            final_files = await _snapshot_files_from_sandbox(runtime_service, sandbox_id=sandbox_id)

        if _builder_model_patch_generation_enabled():
            if _builder_agentic_loop_enabled():
                generation_result, trace_events, final_files, final_entry = await _run_builder_agentic_loop(
                    user_prompt=user_prompt,
                    files=final_files,
                    entry_file=draft.entry_file,
                    request_id=request_id,
                    runtime_service=runtime_service,
                    sandbox_id=sandbox_id,
                )
            else:
                generation_result = await _generate_builder_patch_with_model(
                    user_prompt=user_prompt,
                    files=final_files,
                    entry_file=draft.entry_file,
                )
        else:
            patch_ops, patch_summary = _build_builder_patch_from_prompt(user_prompt, final_files)
            generation_result = BuilderPatchGenerationResult(
                operations=[BuilderPatchOp(**op) for op in patch_ops],
                summary=patch_summary,
            )
        patch_ops_payload = _serialize_patch_ops(generation_result.operations)
        final_files, final_entry = _apply_patch_operations(final_files, final_entry, generation_result.operations)
        if runtime_service is not None and sandbox_id:
            await _apply_patch_operations_to_sandbox(
                runtime_service,
                sandbox_id=sandbox_id,
                operations=generation_result.operations,
            )
            if _builder_chat_commands_enabled():
                command_result = await _run_allowlisted_sandbox_command(
                    runtime_service,
                    sandbox_id=sandbox_id,
                    command=["npm", "run", "build"],
                )
                trace_events.append(
                    _stream_event_payload(
                        event="tool_completed" if command_result.get("ok") else "tool_failed",
                        stage="command",
                        request_id=request_id,
                        data={
                            "tool": "run_command",
                            "command": "npm run build",
                            "status": "ok" if command_result.get("ok") else "failed",
                            "result": command_result,
                        },
                        diagnostics=command_result.get("diagnostics") if not command_result.get("ok") else None,
                    )
                )
                if not command_result.get("ok"):
                    raise _builder_compile_error(
                        "Sandbox command failed",
                        diagnostics=command_result.get("diagnostics") or [{"message": str(command_result.get("message") or "sandbox command failed")}],
                    )
            final_files = await _snapshot_files_from_sandbox(runtime_service, sandbox_id=sandbox_id)

        saved_revision = await _create_draft_revision_from_files(
            db,
            app=app,
            current=draft,
            actor_id=actor_id,
            files=final_files,
            entry_file=final_entry,
        )
        if runtime_service is not None and sandbox_id and actor is not None:
            await runtime_service.sync_session(
                app=app,
                revision=saved_revision,
                user_id=actor.id,
                files=final_files,
                entry_file=final_entry,
            )
    except HTTPException as exc:
        loop_trace_events = getattr(exc, "builder_trace_events", None)
        if isinstance(loop_trace_events, list) and loop_trace_events:
            trace_events = [item for item in loop_trace_events if isinstance(item, dict)]
        _, diagnostics = _extract_http_error_details(exc)
        await _persist_builder_conversation_turn(
            db,
            app_id=app.id,
            revision_id=draft.id,
            actor_id=actor_id,
            request_id=request_id,
            user_prompt=user_prompt,
            status=BuilderConversationTurnStatus.failed,
            generation_result=generation_result,
            trace_events=trace_events,
            diagnostics=diagnostics,
            failure_code=_extract_http_error_code(exc) or "BUILDER_REQUEST_FAILED",
        )
        await db.commit()
        raise
    except Exception as exc:
        await _persist_builder_conversation_turn(
            db,
            app_id=app.id,
            revision_id=draft.id,
            actor_id=actor_id,
            request_id=request_id,
            user_prompt=user_prompt,
            status=BuilderConversationTurnStatus.failed,
            generation_result=generation_result,
            trace_events=trace_events,
            diagnostics=[{"message": str(exc)}],
            failure_code="BUILDER_INTERNAL_ERROR",
        )
        await db.commit()
        raise

    await _persist_builder_conversation_turn(
        db,
        app_id=app.id,
        revision_id=draft.id,
        result_revision_id=saved_revision.id if saved_revision else None,
        actor_id=actor_id,
        request_id=request_id,
        user_prompt=user_prompt,
        status=BuilderConversationTurnStatus.succeeded,
        generation_result=generation_result,
        trace_events=trace_events,
        checkpoint_type=BuilderCheckpointType.auto_run,
        checkpoint_label=f"AI run {request_id[:8]}",
    )
    await db.commit()
    if saved_revision is not None:
        await db.refresh(saved_revision)

    async def event_generator():
        yield ": " + (" " * 2048) + "\n\n"
        yield _stream_event_sse(
            _stream_event_payload(
                event="status",
                stage="start",
                request_id=request_id,
                data={"content": "Builder request accepted"},
                )
            )
        for trace_event in trace_events:
            yield _stream_event_sse(trace_event)

        status_text = f"Applied builder patch: {generation_result.summary}."
        for chunk in status_text.split(" "):
            yield _stream_event_sse(
                _stream_event_payload(
                    event="token",
                    stage="assistant_response",
                    request_id=request_id,
                    data={"content": chunk + " "},
                )
            )
        yield _stream_event_sse(
            _stream_event_payload(
                event="file_changes",
                stage="patch_ready",
                request_id=request_id,
                data={
                    "changed_paths": _collect_changed_paths(generation_result.operations),
                    "operations": patch_ops_payload,
                    "base_revision_id": str(draft.id),
                    "result_revision_id": str(saved_revision.id) if saved_revision else None,
                    "summary": generation_result.summary,
                    "rationale": generation_result.rationale,
                    "assumptions": generation_result.assumptions,
                },
            )
        )
        if saved_revision is not None:
            yield _stream_event_sse(
                _stream_event_payload(
                    event="checkpoint_created",
                    stage="checkpoint",
                    request_id=request_id,
                    data={
                        "revision_id": str(saved_revision.id),
                        "source_revision_id": str(saved_revision.source_revision_id) if saved_revision.source_revision_id else None,
                        "checkpoint_type": "auto_run",
                        "checkpoint_label": f"AI run {request_id[:8]}",
                    },
                )
            )
        yield _stream_event_sse(
            _stream_event_payload(
                event="done",
                stage="complete",
                request_id=request_id,
                include_done_type=True,
            )
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.patch("/{app_id}", response_model=PublishedAppResponse)
async def update_published_app(
    app_id: UUID,
    payload: UpdatePublishedAppRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)

    if payload.name is not None:
        app.name = payload.name.strip()
    if payload.slug is not None:
        next_slug = payload.slug.strip().lower()
        if not APP_SLUG_PATTERN.match(next_slug):
            raise HTTPException(status_code=400, detail="Slug must be lowercase, 3-64 chars, and contain only letters, numbers, hyphens")
        app.slug = next_slug
        if app.status == PublishedAppStatus.published:
            app.published_url = _build_published_url(next_slug)
    if payload.agent_id is not None:
        await _validate_agent(db, ctx["tenant_id"], payload.agent_id)
        app.agent_id = payload.agent_id
    if payload.auth_enabled is not None:
        app.auth_enabled = payload.auth_enabled
    if payload.auth_providers is not None:
        app.auth_providers = _validate_providers(payload.auth_providers)
    if payload.status is not None:
        try:
            app.status = PublishedAppStatus(payload.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status value")

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Published app slug or name already exists")
    await db.refresh(app)
    return _app_to_response(app)


@router.post("/{app_id}/publish", response_model=PublishJobResponse)
async def publish_published_app(
    app_id: UUID,
    request: Request,
    payload: Optional[PublishRequest] = None,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if not _publish_full_build_enabled():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PUBLISH_FULL_BUILD_DISABLED",
                "message": "Publish full-build mode is disabled (`APPS_PUBLISH_FULL_BUILD_ENABLED=0`).",
            },
        )

    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    await _validate_agent(db, ctx["tenant_id"], app.agent_id)
    actor_id = ctx["user"].id if ctx["user"] else None

    payload = payload or PublishRequest()
    current_draft = await _ensure_current_draft_revision(db, app, actor_id)
    if payload.base_revision_id and str(payload.base_revision_id) != str(current_draft.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(current_draft.id),
                "latest_updated_at": current_draft.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )

    source_revision = current_draft
    saved_draft_revision_id: Optional[UUID] = None
    if payload.files is not None or payload.entry_file is not None:
        files = _coerce_files_payload(payload.files or dict(current_draft.files or {}))
        next_entry = _normalize_builder_path(payload.entry_file or current_draft.entry_file)
        _assert_builder_path_allowed(next_entry, field="entry_file")
        _validate_builder_project_or_raise(files, next_entry)
        source_revision = await _create_draft_revision_snapshot(
            db=db,
            app=app,
            current=current_draft,
            actor_id=actor_id,
            files=files,
            entry_file=next_entry,
        )
        saved_draft_revision_id = source_revision.id

    publish_job = PublishedAppPublishJob(
        published_app_id=app.id,
        tenant_id=app.tenant_id,
        requested_by=actor_id,
        source_revision_id=source_revision.id,
        saved_draft_revision_id=saved_draft_revision_id,
        published_revision_id=None,
        status=PublishedAppPublishJobStatus.queued,
        error=None,
        diagnostics=[],
        started_at=None,
        finished_at=None,
    )
    db.add(publish_job)
    await db.flush()
    await db.commit()
    await db.refresh(publish_job)

    enqueue_error = _enqueue_publish_job(job=publish_job)
    if enqueue_error:
        publish_job.status = PublishedAppPublishJobStatus.failed
        publish_job.error = enqueue_error
        publish_job.finished_at = datetime.now(timezone.utc)
        publish_job.diagnostics = [{"message": enqueue_error}]
        await db.commit()
        await db.refresh(publish_job)

    return _publish_job_to_response(publish_job)


@router.get("/{app_id}/publish/jobs/{job_id}", response_model=PublishJobStatusResponse)
async def get_publish_job_status(
    app_id: UUID,
    job_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    job = await _get_publish_job_for_app(db, app_id=app.id, job_id=job_id)
    return PublishJobStatusResponse(**_publish_job_to_response(job).model_dump())


@router.post("/{app_id}/unpublish", response_model=PublishedAppResponse)
async def unpublish_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    app.status = PublishedAppStatus.draft
    app.published_url = None
    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


@router.delete("/{app_id}")
async def delete_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    await db.delete(app)
    await db.commit()
    return {"status": "deleted", "id": str(app_id)}


@router.get("/{app_id}/runtime-preview")
async def runtime_preview(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.read")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)
    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    return {
        "app_id": str(app.id),
        "slug": app.slug,
        "status": app.status.value if hasattr(app.status, "value") else str(app.status),
        "runtime_url": app.published_url or _build_published_url(app.slug),
    }
