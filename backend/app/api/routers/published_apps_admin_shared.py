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
from sqlalchemy import and_, func, select
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
    PublishedAppCustomDomain,
    PublishedAppCustomDomainStatus,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
    PublishedAppSession,
    PublishedAppStatus,
    PublishedAppUserMembership,
    PublishedAppUserMembershipStatus,
    PublishedAppVisibility,
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
from app.services.published_app_auth_templates import (
    get_auth_template,
    list_auth_templates,
)


router = APIRouter(prefix="/admin/apps", tags=["published-apps-admin"])
logger = logging.getLogger(__name__)

APP_SLUG_PATTERN = re.compile(r"^[a-z0-9-]{3,64}$")
DOMAIN_HOST_PATTERN = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
# Path policy: allow editing project files across the workspace, while
# explicitly blocking unsafe/generated/system directories.
BUILDER_ALLOWED_DIR_ROOTS = ()
BUILDER_BLOCKED_DIR_PREFIXES = (
    "node_modules/",
    ".git/",
    ".next/",
    ".vite/",
    ".turbo/",
    ".cache/",
    ".parcel-cache/",
    ".npm/",
    ".pnpm-store/",
    ".yarn/",
    "dist/",
    "build/",
    "coverage/",
    "__pycache__/",
)
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
    description: Optional[str] = None
    logo_url: Optional[str] = None
    slug: str
    status: str
    visibility: str
    auth_enabled: bool
    auth_providers: List[str]
    auth_template_key: str
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


class PublishedAppAuthTemplateResponse(BaseModel):
    key: str
    name: str
    description: str
    thumbnail: str
    tags: List[str]
    style_tokens: Dict[str, str]


class PublishedAppUserResponse(BaseModel):
    user_id: str
    email: str
    full_name: Optional[str] = None
    avatar: Optional[str] = None
    membership_status: str
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    active_sessions: int = 0


class PublishedAppDomainResponse(BaseModel):
    id: str
    host: str
    status: str
    notes: Optional[str] = None
    requested_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


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
    description: Optional[str] = None
    logo_url: Optional[str] = None
    slug: Optional[str] = None
    agent_id: UUID
    template_key: str = "chat-classic"
    visibility: str = "public"
    auth_enabled: bool = True
    auth_providers: List[str] = Field(default_factory=lambda: ["password"])
    auth_template_key: str = "auth-classic"


class UpdatePublishedAppRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    slug: Optional[str] = None
    agent_id: Optional[UUID] = None
    visibility: Optional[str] = None
    auth_enabled: Optional[bool] = None
    auth_providers: Optional[List[str]] = None
    auth_template_key: Optional[str] = None
    status: Optional[str] = None


class UpdatePublishedAppUserRequest(BaseModel):
    membership_status: str


class CreatePublishedAppDomainRequest(BaseModel):
    host: str
    notes: Optional[str] = None


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


def _validate_auth_template_key(auth_template_key: str) -> str:
    key = auth_template_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="auth_template_key is required")
    try:
        get_auth_template(key)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unsupported auth_template_key: {key}")
    return key


def _validate_visibility(value: str) -> str:
    normalized = (value or "").strip().lower()
    try:
        return PublishedAppVisibility(normalized).value
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported visibility value")


def _validate_providers(providers: List[str]) -> List[str]:
    normalized = [p.strip().lower() for p in providers if p and p.strip()]
    if not normalized:
        raise HTTPException(status_code=400, detail="At least one auth provider must be configured")
    allowed = {"password", "google"}
    invalid = [p for p in normalized if p not in allowed]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported auth providers: {', '.join(invalid)}")
    return sorted(set(normalized))


def _normalize_domain_host(host: str) -> str:
    normalized = (host or "").strip().lower().rstrip(".")
    if not normalized:
        raise HTTPException(status_code=400, detail="Domain host is required")
    if not DOMAIN_HOST_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail="Domain host is invalid")
    return normalized


def _app_to_response(app: PublishedApp) -> PublishedAppResponse:
    return PublishedAppResponse(
        id=str(app.id),
        tenant_id=str(app.tenant_id),
        agent_id=str(app.agent_id),
        name=app.name,
        description=app.description,
        logo_url=app.logo_url,
        slug=app.slug,
        status=app.status.value if hasattr(app.status, "value") else str(app.status),
        visibility=app.visibility.value if hasattr(app.visibility, "value") else str(app.visibility or "public"),
        auth_enabled=bool(app.auth_enabled),
        auth_providers=list(app.auth_providers or []),
        auth_template_key=app.auth_template_key or "auth-classic",
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


def _auth_template_to_response(template) -> PublishedAppAuthTemplateResponse:
    return PublishedAppAuthTemplateResponse(
        key=template.key,
        name=template.name,
        description=template.description,
        thumbnail=template.thumbnail,
        tags=list(template.tags),
        style_tokens=dict(template.style_tokens),
    )


def _domain_to_response(domain: PublishedAppCustomDomain) -> PublishedAppDomainResponse:
    return PublishedAppDomainResponse(
        id=str(domain.id),
        host=domain.host,
        status=domain.status.value if hasattr(domain.status, "value") else str(domain.status),
        notes=domain.notes,
        requested_by=str(domain.requested_by) if domain.requested_by else None,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
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
