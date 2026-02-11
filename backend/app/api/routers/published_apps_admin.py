import json
import os
import re
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import PurePosixPath
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
    BuilderConversationTurnStatus,
    PublishedApp,
    PublishedAppBuilderConversationTurn,
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
from app.services.published_app_templates import (
    build_template_files,
    get_template,
    list_templates,
)


router = APIRouter(prefix="/admin/apps", tags=["published-apps-admin"])

APP_SLUG_PATTERN = re.compile(r"^[a-z0-9-]{3,64}$")
BUILDER_ALLOWED_DIR_ROOTS = ("src/", "public/")
BUILDER_ALLOWED_ROOT_FILES = {
    "index.html",
    "package.json",
    "package-lock.json",
    "vite.config.ts",
}
BUILDER_ALLOWED_ROOT_GLOBS = ("tsconfig*.json", "postcss.config.*", "tailwind.config.*")
BUILDER_ALLOWED_EXTENSIONS = {
    ".html",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".json",
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
BUILDER_MAX_PROJECT_BYTES = int(os.getenv("BUILDER_MAX_PROJECT_BYTES", str(2 * 1024 * 1024)))
BUILDER_MODEL_NAME = os.getenv("BUILDER_MODEL_NAME", "gpt-5-mini")
BUILDER_MODEL_MAX_RETRIES = int(os.getenv("BUILDER_MODEL_MAX_RETRIES", "2"))
BUILDER_CONTEXT_MAX_FILES = int(os.getenv("BUILDER_CONTEXT_MAX_FILES", "14"))
BUILDER_CONTEXT_MAX_FILE_BYTES = int(os.getenv("BUILDER_CONTEXT_MAX_FILE_BYTES", str(24 * 1024)))
BUILDER_AGENT_MAX_ITERATIONS = int(os.getenv("BUILDER_AGENT_MAX_ITERATIONS", "3"))
BUILDER_AGENT_MAX_SEARCH_RESULTS = int(os.getenv("BUILDER_AGENT_MAX_SEARCH_RESULTS", "8"))
IMPORT_RE = re.compile(r'^\s*(?:import|export)\s+(?:[^"\']*?\s+from\s+)?["\']([^"\']+)["\']', re.MULTILINE)


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


class BuilderConversationTurnResponse(BaseModel):
    id: str
    published_app_id: str
    revision_id: Optional[str] = None
    request_id: str
    status: str
    user_prompt: str
    assistant_summary: Optional[str] = None
    assistant_rationale: Optional[str] = None
    assistant_assumptions: List[str] = Field(default_factory=list)
    patch_operations: List[Dict[str, Any]] = Field(default_factory=list)
    tool_trace: List[Dict[str, Any]] = Field(default_factory=list)
    diagnostics: List[Dict[str, str]] = Field(default_factory=list)
    failure_code: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime


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
    _enqueue_revision_build(revision=created, app=app, build_kind="draft")
    return created


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


def _builder_publish_build_guard_enabled() -> bool:
    return _env_flag("APPS_BUILDER_PUBLISH_BUILD_GUARD_ENABLED", False)


def _enqueue_revision_build(
    *,
    revision: PublishedAppRevision,
    app: PublishedApp,
    build_kind: str,
) -> None:
    if not _builder_auto_enqueue_enabled():
        return
    try:
        from app.workers.tasks import build_published_app_revision_task
    except Exception:
        return

    build_published_app_revision_task.delay(
        revision_id=str(revision.id),
        tenant_id=str(app.tenant_id),
        app_id=str(app.id),
        slug=app.slug,
        build_kind=build_kind,
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


def _serialize_patch_ops(operations: List[BuilderPatchOp]) -> List[Dict[str, Any]]:
    return [op.model_dump(exclude_none=True) for op in operations]


def _builder_conversation_to_response(turn: PublishedAppBuilderConversationTurn) -> BuilderConversationTurnResponse:
    return BuilderConversationTurnResponse(
        id=str(turn.id),
        published_app_id=str(turn.published_app_id),
        revision_id=str(turn.revision_id) if turn.revision_id else None,
        request_id=turn.request_id,
        status=turn.status.value if hasattr(turn.status, "value") else str(turn.status),
        user_prompt=turn.user_prompt,
        assistant_summary=turn.assistant_summary,
        assistant_rationale=turn.assistant_rationale,
        assistant_assumptions=list(turn.assistant_assumptions or []),
        patch_operations=list(turn.patch_operations or []),
        tool_trace=list(turn.tool_trace or []),
        diagnostics=list(turn.diagnostics or []),
        failure_code=turn.failure_code,
        created_by=str(turn.created_by) if turn.created_by else None,
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
) -> None:
    turn = PublishedAppBuilderConversationTurn(
        published_app_id=app_id,
        revision_id=revision_id,
        request_id=request_id,
        status=status,
        user_prompt=user_prompt,
        assistant_summary=generation_result.summary if generation_result else None,
        assistant_rationale=generation_result.rationale if generation_result else None,
        assistant_assumptions=list(generation_result.assumptions) if generation_result else [],
        patch_operations=_serialize_patch_ops(generation_result.operations) if generation_result else [],
        tool_trace=list(trace_events or []),
        diagnostics=list(diagnostics or []),
        failure_code=failure_code,
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


def _builder_tool_run_targeted_tests(changed_paths: List[str]) -> Dict[str, Any]:
    return {
        "ok": True,
        "status": "skipped",
        "message": "targeted tests are not configured for builder drafts yet",
        "changed_paths": changed_paths[:6],
    }


async def _run_builder_agentic_loop(
    *,
    user_prompt: str,
    files: Dict[str, str],
    entry_file: str,
    request_id: str,
) -> tuple[BuilderPatchGenerationResult, List[Dict[str, Any]]]:
    trace_events: List[Dict[str, Any]] = []
    repair_feedback: List[str] = []
    recent_paths: List[str] = []
    aggregate_ops: List[BuilderPatchOp] = []
    working_files = dict(files)
    working_entry = entry_file
    last_result: Optional[BuilderPatchGenerationResult] = None

    for iteration in range(1, BUILDER_AGENT_MAX_ITERATIONS + 1):
        trace_events.append(
            _stream_event_payload(
                event="tool",
                stage="inspect",
                request_id=request_id,
                data={
                    "tool": "list_files",
                    "status": "ok",
                    "iteration": iteration,
                    "result": _builder_tool_list_files(working_files),
                },
            )
        )
        if recent_paths:
            trace_events.append(
                _stream_event_payload(
                    event="tool",
                    stage="inspect",
                    request_id=request_id,
                    data={
                        "tool": "read_file",
                        "status": "ok",
                        "iteration": iteration,
                        "result": _builder_tool_read_file(working_files, recent_paths[-1]),
                    },
                )
            )
        trace_events.append(
            _stream_event_payload(
                event="tool",
                stage="inspect",
                request_id=request_id,
                data={
                    "tool": "search_code",
                    "status": "ok",
                    "iteration": iteration,
                    "result": _builder_tool_search_code(working_files, user_prompt),
                },
            )
        )

        result = await _generate_builder_patch_with_model(
            user_prompt=user_prompt,
            files=working_files,
            entry_file=working_entry,
            repair_feedback=repair_feedback,
            recent_paths=recent_paths,
        )
        last_result = result

        dry_run_result = _builder_tool_apply_patch_dry_run(
            working_files,
            working_entry,
            result.operations,
        )
        trace_events.append(
            _stream_event_payload(
                event="tool",
                stage="patch_dry_run",
                request_id=request_id,
                data={
                    "tool": "apply_patch_dry_run",
                    "status": "ok" if dry_run_result.get("ok") else "failed",
                    "iteration": iteration,
                    "result": dry_run_result,
                },
                diagnostics=dry_run_result.get("diagnostics") if not dry_run_result.get("ok") else None,
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

        compile_result = _builder_tool_compile_project(working_files, working_entry)
        trace_events.append(
            _stream_event_payload(
                event="tool",
                stage="compile",
                request_id=request_id,
                data={
                    "tool": "compile_project",
                    "status": "ok" if compile_result.get("ok") else "failed",
                    "iteration": iteration,
                    "result": compile_result,
                },
                diagnostics=compile_result.get("diagnostics") if not compile_result.get("ok") else None,
            )
        )
        if not compile_result.get("ok"):
            repair_feedback.append(str(compile_result.get("message") or "compile failed"))
            continue

        test_result = _builder_tool_run_targeted_tests(recent_paths)
        trace_events.append(
            _stream_event_payload(
                event="tool",
                stage="test",
                request_id=request_id,
                data={
                    "tool": "run_targeted_tests",
                    "status": "ok",
                    "iteration": iteration,
                    "result": test_result,
                },
            )
        )

        return (
            BuilderPatchGenerationResult(
                operations=aggregate_ops,
                summary=result.summary,
                rationale=result.rationale,
                assumptions=result.assumptions,
            ),
            trace_events,
        )

    if last_result is not None and aggregate_ops:
        return (
            BuilderPatchGenerationResult(
                operations=aggregate_ops,
                summary=last_result.summary,
                rationale=last_result.rationale,
                assumptions=last_result.assumptions,
            ),
            trace_events,
        )

    raise _builder_compile_error(
        "Agentic loop could not produce a valid patch",
        diagnostics=[{"message": item} for item in repair_feedback[-6:]] or [{"message": "No valid patch generated"}],
    )


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
        f"{normalized}.jsx",
        f"{normalized}.js",
        f"{normalized}.css",
        f"{normalized}/index.tsx",
        f"{normalized}/index.ts",
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
        if encoded_size > BUILDER_MAX_FILE_BYTES:
            raise _builder_policy_error(
                f"File exceeds size limit ({BUILDER_MAX_FILE_BYTES} bytes): {path}",
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
        if PurePosixPath(path).suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
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
        _enqueue_revision_build(revision=revision, app=app, build_kind="draft")

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
    _enqueue_revision_build(revision=revision, app=app, build_kind="draft")
    await db.commit()
    await db.refresh(app)
    await db.refresh(revision)
    return _revision_to_response(revision)


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
    _enqueue_revision_build(
        revision=revision,
        app=app,
        build_kind=revision.kind.value if hasattr(revision.kind, "value") else str(revision.kind),
    )
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
    _enqueue_revision_build(revision=revision, app=app, build_kind="draft")

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
    actor_id = ctx["user"].id if ctx["user"] else None
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
    try:
        if _builder_model_patch_generation_enabled():
            if _builder_agentic_loop_enabled():
                generation_result, trace_events = await _run_builder_agentic_loop(
                    user_prompt=user_prompt,
                    files=existing_files,
                    entry_file=draft.entry_file,
                    request_id=request_id,
                )
            else:
                generation_result = await _generate_builder_patch_with_model(
                    user_prompt=user_prompt,
                    files=existing_files,
                    entry_file=draft.entry_file,
                )
        else:
            patch_ops, patch_summary = _build_builder_patch_from_prompt(user_prompt, existing_files)
            generation_result = BuilderPatchGenerationResult(
                operations=[BuilderPatchOp(**op) for op in patch_ops],
                summary=patch_summary,
            )
        patch_ops_payload = _serialize_patch_ops(generation_result.operations)
        _apply_patch_operations(existing_files, draft.entry_file, generation_result.operations)
    except HTTPException as exc:
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
        actor_id=actor_id,
        request_id=request_id,
        user_prompt=user_prompt,
        status=BuilderConversationTurnStatus.succeeded,
        generation_result=generation_result,
        trace_events=trace_events,
    )
    await db.commit()

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
                event="patch_ops",
                stage="patch_ready",
                request_id=request_id,
                data={
                    "operations": patch_ops_payload,
                    "base_revision_id": str(draft.id),
                    "summary": generation_result.summary,
                    "rationale": generation_result.rationale,
                    "assumptions": generation_result.assumptions,
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


@router.post("/{app_id}/publish", response_model=PublishedAppResponse)
async def publish_published_app(
    app_id: UUID,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    await _validate_agent(db, ctx["tenant_id"], app.agent_id)
    actor_id = ctx["user"].id if ctx["user"] else None

    current_draft = await _ensure_current_draft_revision(db, app, actor_id)
    current_draft_id = str(current_draft.id)
    if _builder_publish_build_guard_enabled():
        current_build_status = (
            current_draft.build_status.value
            if hasattr(current_draft.build_status, "value")
            else str(current_draft.build_status)
        )
        if current_build_status in {
            PublishedAppRevisionBuildStatus.queued.value,
            PublishedAppRevisionBuildStatus.running.value,
        }:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "BUILD_PENDING",
                    "message": "Draft build is still in progress",
                    "build_status": current_build_status,
                    "revision_id": current_draft_id,
                },
            )
        if current_build_status == PublishedAppRevisionBuildStatus.failed.value:
            diagnostics = []
            if current_draft.build_error:
                diagnostics.append({"message": current_draft.build_error})
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "BUILD_FAILED",
                    "message": "Draft build failed",
                    "build_status": current_build_status,
                    "revision_id": current_draft_id,
                    "diagnostics": diagnostics,
                },
            )
    published_revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.published,
        template_key=current_draft.template_key,
        entry_file=current_draft.entry_file,
        files=dict(current_draft.files or {}),
        build_status=current_draft.build_status,
        build_seq=current_draft.build_seq,
        build_error=current_draft.build_error,
        build_started_at=current_draft.build_started_at,
        build_finished_at=current_draft.build_finished_at,
        dist_storage_prefix=None,
        dist_manifest=dict(current_draft.dist_manifest or {}) if current_draft.dist_manifest else None,
        template_runtime=current_draft.template_runtime or "vite_static",
        compiled_bundle=current_draft.compiled_bundle,
        bundle_hash=current_draft.bundle_hash,
        source_revision_id=current_draft.id,
        created_by=actor_id,
    )
    db.add(published_revision)
    await db.flush()

    try:
        promoted_prefix = _promote_revision_dist_artifacts(
            app=app,
            source_revision=current_draft,
            destination_revision=published_revision,
        )
        if promoted_prefix:
            published_revision.dist_storage_prefix = promoted_prefix
    except (PublishedAppBundleStorageError, ValueError) as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "BUILD_ARTIFACT_COPY_FAILED",
                "message": "Failed to promote build artifacts during publish",
                "revision_id": current_draft_id,
                "error": str(exc),
            },
        )

    app.current_published_revision_id = published_revision.id
    app.status = PublishedAppStatus.published
    app.published_at = datetime.now(timezone.utc)
    app.published_url = _build_published_url(app.slug)
    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


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
