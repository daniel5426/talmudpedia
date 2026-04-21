from __future__ import annotations

import logging
import os
import re
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ALGORITHM, SECRET_KEY, create_access_token, verify_password
from app.db.postgres.models.identity import OrgMembership, Organization, User
from app.db.postgres.models.workspace import Project
from app.db.postgres.session import get_db
from app.services.auth_context_service import (
    list_organization_projects,
    list_user_organizations,
    resolve_effective_scopes,
    serialize_organization_summary,
    serialize_project_summary,
    serialize_user_summary,
)
from app.services.workos_auth_service import LocalSessionBundle, WorkOSAuthError, WorkOSAuthService

router = APIRouter()
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)


class SessionUserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    avatar: str | None = None
    role: str = "user"


class OrganizationSummaryResponse(BaseModel):
    id: str
    name: str
    status: str


class ProjectSummaryResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None = None
    status: str
    is_default: bool = False


class SessionResponse(BaseModel):
    authenticated: bool = True
    onboarding_required: bool = False
    user: SessionUserResponse
    active_organization: OrganizationSummaryResponse | None = None
    active_project: ProjectSummaryResponse | None = None
    organizations: list[OrganizationSummaryResponse]
    projects: list[ProjectSummaryResponse]
    effective_scopes: list[str]


class SwitchOrganizationRequest(BaseModel):
    organization_id: UUID
    return_to: str | None = None


class SwitchProjectRequest(BaseModel):
    project_id: UUID


class OnboardingOrganizationRequest(BaseModel):
    name: str
    return_to: str | None = None


async def _resolve_user_from_access_token(token: str, db: AsyncSession) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = UUID(str(payload.get("sub")))
    except Exception as exc:
        raise credentials_exception from exc

    user = await db.get(User, user_id)
    if user is None:
        raise credentials_exception
    return user


def _slugify_organization_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return cleaned[:48] or "organization"


def _frontend_request_origin(request: Request) -> str:
    explicit = str(os.getenv("NEXT_PUBLIC_APP_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")

    referer = str(request.headers.get("referer") or "").strip()
    if referer.startswith("http://") or referer.startswith("https://"):
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    origin = str(request.headers.get("origin") or "").strip()
    if origin.startswith("http://") or origin.startswith("https://"):
        parsed = urlparse(origin)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    return str(request.base_url).rstrip("/")


def _normalize_frontend_return_to(return_to: str | None, request: Request, *, fallback: str) -> str:
    resolved = str(return_to or "").strip() or fallback
    if resolved.startswith("http://") or resolved.startswith("https://"):
        return resolved
    return f"{_frontend_request_origin(request)}{resolved if resolved.startswith('/') else f'/{resolved}'}"


def _build_frontend_onboarding_url(return_to: str, request: Request) -> str:
    if return_to.startswith("http://") or return_to.startswith("https://"):
        parsed = urlparse(return_to)
        query = urlencode({"return_to": return_to})
        return urlunparse((parsed.scheme, parsed.netloc, "/auth/onboarding", "", query, ""))
    query = urlencode({"return_to": return_to})
    return f"{_frontend_request_origin(request)}/auth/onboarding?{query}"


def _fingerprint_secret(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _append_workos_callback_log(
    event: str,
    *,
    request: Request,
    fields: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "event": event,
        "pid": os.getpid(),
        "path": request.url.path,
        "query": request.url.query,
        "host": str(request.headers.get("host") or "").strip(),
        "origin": str(request.headers.get("origin") or "").strip(),
        "referer": str(request.headers.get("referer") or "").strip(),
        "cookie_present": bool(str(request.cookies.get("wos_session") or "").strip()),
        "cookie_fp": _fingerprint_secret(str(request.cookies.get("wos_session") or "").strip()),
        "workos_client_id_fp": _fingerprint_secret(os.getenv("WORKOS_CLIENT_ID")),
        "workos_cookie_password_fp": _fingerprint_secret(os.getenv("WORKOS_COOKIE_PASSWORD")),
    }
    if fields:
        payload.update(fields)
    try:
        from pathlib import Path
        path = Path(os.getenv("WORKOS_AUTH_DEBUG_LOG_PATH", "/tmp/talmudpedia-workos-auth.jsonl").strip() or "/tmp/talmudpedia-workos-auth.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            import json
            handle.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")
    except Exception:
        logger.exception("Failed to append WorkOS callback debug log")


async def _load_workos_auth(
    *,
    request: Request,
    response: Response,
    db: AsyncSession,
) -> tuple[WorkOSAuthService, object, User]:
    service = WorkOSAuthService(db)
    auth_response = await service.authenticate_request(request, response)
    if auth_response is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = await service.sync_local_user(auth_response)
    return service, auth_response, user


async def _load_workos_session_bundle(
    *,
    request: Request,
    response: Response,
    db: AsyncSession,
) -> LocalSessionBundle:
    service, auth_response, _ = await _load_workos_auth(request=request, response=response, db=db)
    if not service.current_organization_id(auth_response):
        raise HTTPException(status_code=409, detail="Organization onboarding is required")
    bundle = await service.ensure_local_bundle(auth_response=auth_response, request=request)
    service.set_project_cookie(response=response, request=request, project_id=bundle.project.id)
    return bundle


async def _serialize_session_response(
    *,
    db: AsyncSession,
    user: User,
    organization: Organization | None,
    project: Project | None,
    effective_scopes: list[str],
    authenticated: bool = True,
    onboarding_required: bool = False,
) -> SessionResponse:
    organizations = await list_user_organizations(db=db, user_id=user.id)
    projects = await list_organization_projects(db=db, organization_id=organization.id) if organization is not None else []
    return SessionResponse(
        authenticated=authenticated,
        onboarding_required=onboarding_required,
        user=SessionUserResponse.model_validate(serialize_user_summary(user)),
        active_organization=(
            OrganizationSummaryResponse.model_validate(serialize_organization_summary(organization))
            if organization is not None
            else None
        ),
        active_project=(
            ProjectSummaryResponse.model_validate(serialize_project_summary(project))
            if project is not None
            else None
        ),
        organizations=[OrganizationSummaryResponse.model_validate(serialize_organization_summary(item)) for item in organizations],
        projects=[ProjectSummaryResponse.model_validate(serialize_project_summary(item)) for item in projects],
        effective_scopes=effective_scopes,
    )


async def get_current_user(
    request: Request,
    response: Response,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if token:
        return await _resolve_user_from_access_token(token, db)
    if WorkOSAuthService.is_enabled():
        _, _, user = await _load_workos_auth(request=request, response=response, db=db)
        return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/login")
@router.post("/login")
async def login(request: Request, db: AsyncSession = Depends(get_db)):
    service = WorkOSAuthService(db)
    if not service.is_enabled():
        raise HTTPException(status_code=503, detail="WorkOS auth is not configured")
    url = service.build_authorization_url(
        request,
        screen_hint="sign-in",
        return_to=_normalize_frontend_return_to(
            request.query_params.get("return_to"),
            request,
            fallback="/admin/agents/playground",
        ),
    )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/signup")
@router.post("/signup")
async def signup(request: Request, db: AsyncSession = Depends(get_db)):
    service = WorkOSAuthService(db)
    if not service.is_enabled():
        raise HTTPException(status_code=503, detail="WorkOS auth is not configured")
    url = service.build_authorization_url(
        request,
        screen_hint="sign-up",
        return_to=_normalize_frontend_return_to(
            request.query_params.get("return_to"),
            request,
            fallback="/admin/agents/playground",
        ),
    )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/register")
@router.post("/register")
async def register(request: Request, db: AsyncSession = Depends(get_db)):
    service = WorkOSAuthService(db)
    if not service.is_enabled():
        raise HTTPException(status_code=503, detail="WorkOS auth is not configured")
    url = service.build_authorization_url(
        request,
        screen_hint="sign-up",
        return_to=_normalize_frontend_return_to(
            request.query_params.get("return_to"),
            request,
            fallback="/admin/agents/playground",
        ),
    )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def auth_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = WorkOSAuthService(db)
    _append_workos_callback_log("auth_callback.start", request=request)
    if error:
        raise HTTPException(status_code=400, detail=error_description or error)
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    decoded_state = service.decode_state(state)
    auth_response = await service.authenticate_with_code(
        request,
        code=code,
        invitation_token=decoded_state.get("invitation_token"),
    )
    await service.sync_local_user(auth_response)

    redirect_to = _normalize_frontend_return_to(
        decoded_state.get("return_to"),
        request,
        fallback="/admin/agents/playground",
    )
    if service.current_organization_id(auth_response):
        await service.sync_current_organization(auth_response=auth_response)
        bundle = await service.ensure_local_bundle(auth_response=auth_response, request=request)
        redirect_response = RedirectResponse(url=redirect_to, status_code=status.HTTP_302_FOUND)
        service.set_project_cookie(response=redirect_response, request=request, project_id=bundle.project.id)
    else:
        redirect_response = RedirectResponse(
            url=_build_frontend_onboarding_url(redirect_to, request),
            status_code=status.HTTP_302_FOUND,
        )

    sealed_session = (
        auth_response.get("sealed_session")
        if isinstance(auth_response, dict)
        else getattr(auth_response, "sealed_session", None) or getattr(auth_response, "sealedSession", None)
    )
    if sealed_session:
        service.set_session_cookie(response=redirect_response, request=request, sealed_session=str(sealed_session))
        _append_workos_callback_log(
            "auth_callback.session_cookie_set",
            request=request,
            fields={
                "redirect_to": redirect_to,
                "new_cookie_fp": _fingerprint_secret(str(sealed_session)),
            },
        )
    else:
        _append_workos_callback_log(
            "auth_callback.session_cookie_missing",
            request=request,
            fields={"redirect_to": redirect_to},
        )
    return redirect_response


@router.get("/session", response_model=SessionResponse)
async def get_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service, auth_response, user = await _load_workos_auth(request=request, response=response, db=db)
    if not service.current_organization_id(auth_response):
        return await _serialize_session_response(
            db=db,
            user=user,
            organization=None,
            project=None,
            effective_scopes=[],
            authenticated=True,
            onboarding_required=True,
        )

    bundle = await service.ensure_local_bundle(auth_response=auth_response, request=request)
    service.set_project_cookie(response=response, request=request, project_id=bundle.project.id)
    effective_scopes = await resolve_effective_scopes(
        db=db,
        user=bundle.user,
        organization_id=bundle.organization.id,
        project_id=bundle.project.id,
    )
    return await _serialize_session_response(
        db=db,
        user=bundle.user,
        organization=bundle.organization,
        project=bundle.project,
        effective_scopes=effective_scopes,
        authenticated=True,
        onboarding_required=False,
    )


@router.post("/onboarding/organization", response_model=SessionResponse)
async def create_onboarding_organization(
    payload: OnboardingOrganizationRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service, auth_response, user = await _load_workos_auth(request=request, response=response, db=db)
    if service.current_organization_id(auth_response):
        bundle = await service.ensure_local_bundle(auth_response=auth_response, request=request)
        effective_scopes = await resolve_effective_scopes(
            db=db,
            user=bundle.user,
            organization_id=bundle.organization.id,
            project_id=bundle.project.id,
        )
        return await _serialize_session_response(
            db=db,
            user=bundle.user,
            organization=bundle.organization,
            project=bundle.project,
            effective_scopes=effective_scopes,
        )

    name = str(payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Organization name is required")

    bundle = await service.create_organization_for_user(
        local_user=user,
        name=name,
        request=request,
        response=response,
        return_to=payload.return_to,
    )
    if isinstance(bundle, dict):
        return JSONResponse(bundle)
    effective_scopes = await resolve_effective_scopes(
        db=db,
        user=bundle.user,
        organization_id=bundle.organization.id,
        project_id=bundle.project.id,
    )
    return await _serialize_session_response(
        db=db,
        user=bundle.user,
        organization=bundle.organization,
        project=bundle.project,
        effective_scopes=effective_scopes,
    )


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return serialize_user_summary(current_user)


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    service = WorkOSAuthService(db)
    frontend_home = _normalize_frontend_return_to("/", request, fallback="/")
    logout_url = None
    result = JSONResponse({"status": "logged_out", "logout_url": frontend_home})
    if service.is_enabled():
        logout_url = service.get_logout_url(request, return_to=frontend_home)
        result = JSONResponse({"status": "logged_out", "logout_url": logout_url or frontend_home})
        service.clear_session_cookie(response=result, request=request)
        service.clear_project_cookie(response=result, request=request)
    return result


@router.post("/context/organization")
async def switch_active_organization(
    payload: SwitchOrganizationRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service, auth_response, user = await _load_workos_auth(request=request, response=response, db=db)

    organization = (
        await db.execute(
            select(Organization)
            .join(OrgMembership, OrgMembership.organization_id == Organization.id)
            .where(
                Organization.id == payload.organization_id,
                OrgMembership.user_id == user.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not organization.workos_organization_id:
        raise HTTPException(status_code=400, detail="Organization is not linked to WorkOS")

    refreshed = await service.switch_organization(
        request,
        response,
        organization.workos_organization_id,
        return_to=payload.return_to or str(request.headers.get("referer") or "").strip() or request.query_params.get("return_to"),
    )
    if isinstance(refreshed, dict):
        return JSONResponse(refreshed)

    await service.sync_current_organization(auth_response=refreshed, actor_user_id=user.id)
    bundle = await service.ensure_local_bundle(auth_response=refreshed, request=request, actor_user_id=user.id)
    service.set_project_cookie(response=response, request=request, project_id=bundle.project.id)
    effective_scopes = await resolve_effective_scopes(
        db=db,
        user=bundle.user,
        organization_id=bundle.organization.id,
        project_id=bundle.project.id,
    )
    return await _serialize_session_response(
        db=db,
        user=bundle.user,
        organization=bundle.organization,
        project=bundle.project,
        effective_scopes=effective_scopes,
    )


@router.post("/context/project", response_model=SessionResponse)
async def switch_active_project(
    payload: SwitchProjectRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    bundle = await _load_workos_session_bundle(
        request=request,
        response=response,
        db=db,
    )
    project = (
        await db.execute(
            select(Project).where(
                Project.organization_id == bundle.organization.id,
                Project.id == payload.project_id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    WorkOSAuthService(db).set_project_cookie(response=response, request=request, project_id=project.id)
    effective_scopes = await resolve_effective_scopes(
        db=db,
        user=bundle.user,
        organization_id=bundle.organization.id,
        project_id=project.id,
    )
    return await _serialize_session_response(
        db=db,
        user=bundle.user,
        organization=bundle.organization,
        project=project,
        effective_scopes=effective_scopes,
    )


@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    del form_data, db
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Local password token login has been removed")
