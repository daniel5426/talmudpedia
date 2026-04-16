from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, Optional
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ALGORITHM, SECRET_KEY, create_access_token, get_password_hash, verify_password
from app.db.postgres.models.identity import OrgMembership, OrgInvite, Tenant, User
from app.db.postgres.models.workspace import BrowserSession, Project
from app.db.postgres.session import get_db
from app.services.auth_context_service import (
    list_organization_projects,
    list_user_organizations,
    resolve_effective_scopes,
    serialize_organization_summary,
    serialize_project_summary,
    serialize_user_summary,
)
from app.services.browser_session_service import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_DAYS,
    BrowserSessionService,
)
from app.services.organization_bootstrap_service import OrganizationBootstrapService

router = APIRouter()
logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
AUTH_SESSION_SLOW_LOG_THRESHOLD_MS = int(
    (os.getenv("AUTH_SESSION_SLOW_LOG_THRESHOLD_MS") or "500").strip() or "500"
)
AUTH_SESSION_LOG_ALL = str(os.getenv("AUTH_SESSION_LOG_ALL") or "").strip().lower() in {"1", "true", "yes", "on"}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


class SessionUserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    avatar: str | None = None
    role: str = "user"


class OrganizationSummaryResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str


class ProjectSummaryResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    slug: str
    description: str | None = None
    status: str
    is_default: bool = False


class SessionResponse(BaseModel):
    user: SessionUserResponse
    active_organization: OrganizationSummaryResponse
    active_project: ProjectSummaryResponse
    organizations: list[OrganizationSummaryResponse]
    projects: list[ProjectSummaryResponse]
    effective_scopes: list[str]


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class GoogleToken(BaseModel):
    credential: str


class SwitchOrganizationRequest(BaseModel):
    organization_slug: str


class SwitchProjectRequest(BaseModel):
    project_slug: str


class _SessionBundle(BaseModel):
    user: SessionUserResponse
    active_organization: OrganizationSummaryResponse
    active_project: ProjectSummaryResponse
    organizations: list[OrganizationSummaryResponse]
    projects: list[ProjectSummaryResponse]
    effective_scopes: list[str]


_user_cache: Dict[str, Any] = {}
CACHE_TTL = 300


def _slugify(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return cleaned[:48] or fallback


def _session_cookie_samesite() -> str:
    # Hosted prod currently serves the frontend and API from different sites,
    # so browser session cookies must be cross-site capable over HTTPS.
    api_base_url = (os.getenv("API_BASE_URL") or "").strip().lower()
    platform_base_url = (os.getenv("PLATFORM_BASE_URL") or "").strip().lower()
    if api_base_url.startswith("https://") and platform_base_url.startswith("https://"):
        return "none"
    return "lax"


def _set_session_cookie(*, response: Response, request: Request, token: str) -> None:
    max_age_seconds = SESSION_TTL_DAYS * 24 * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite=_session_cookie_samesite(),
        path="/",
        max_age=max_age_seconds,
        expires=max_age_seconds,
    )


def _clear_session_cookie(*, response: Response, request: Request) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=request.url.scheme == "https",
        samesite=_session_cookie_samesite(),
    )


async def _resolve_user_from_access_token(token: str, db: AsyncSession) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception

        now = time.time()
        if user_id_str in _user_cache:
            cached_user, expires_at = _user_cache[user_id_str]
            if now < expires_at:
                return cached_user
            del _user_cache[user_id_str]

        try:
            user_id = UUID(user_id_str)
        except ValueError as exc:
            raise credentials_exception from exc
    except jwt.PyJWTError as exc:
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    db.expunge(user)
    _user_cache[user_id_str] = (user, time.time() + CACHE_TTL)
    return user


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if token:
        return await _resolve_user_from_access_token(token, db)

    cookie_token = str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if cookie_token:
        session = await BrowserSessionService(db).resolve_session(cookie_token)
        if session is not None:
            user = await db.get(User, session.user_id)
            if user is not None:
                return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _load_browser_session_bundle(request: Request, db: AsyncSession) -> tuple[BrowserSession, _SessionBundle]:
    started_at = time.perf_counter()
    timings_ms: dict[str, int] = {}

    def record_timing(step: str, step_started_at: float) -> None:
        timings_ms[step] = int((time.perf_counter() - step_started_at) * 1000)

    raw_token = str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail="No active browser session")

    session: BrowserSession | None = None
    user: User | None = None
    organization: Tenant | None = None
    project: Project | None = None
    try:
        step_started_at = time.perf_counter()
        session = await BrowserSessionService(db).resolve_session(raw_token)
        record_timing("resolve_session", step_started_at)
        if session is None:
            raise HTTPException(status_code=401, detail="Browser session expired")

        step_started_at = time.perf_counter()
        user = await db.get(User, session.user_id)
        record_timing("load_user", step_started_at)

        step_started_at = time.perf_counter()
        organization = await db.get(Tenant, session.organization_id)
        record_timing("load_organization", step_started_at)

        step_started_at = time.perf_counter()
        project = await db.get(Project, session.project_id)
        record_timing("load_project", step_started_at)
        if user is None or organization is None or project is None:
            raise HTTPException(status_code=401, detail="Browser session is invalid")

        step_started_at = time.perf_counter()
        organizations = await list_user_organizations(db=db, user_id=user.id)
        record_timing("list_user_organizations", step_started_at)

        step_started_at = time.perf_counter()
        projects = await list_organization_projects(db=db, organization_id=organization.id)
        record_timing("list_organization_projects", step_started_at)

        step_started_at = time.perf_counter()
        effective_scopes = await resolve_effective_scopes(
            db=db,
            user=user,
            organization_id=organization.id,
            project_id=project.id,
        )
        record_timing("resolve_effective_scopes", step_started_at)

        bundle = _SessionBundle(
            user=SessionUserResponse.model_validate(serialize_user_summary(user)),
            active_organization=OrganizationSummaryResponse.model_validate(serialize_organization_summary(organization)),
            active_project=ProjectSummaryResponse.model_validate(serialize_project_summary(project)),
            organizations=[OrganizationSummaryResponse.model_validate(serialize_organization_summary(item)) for item in organizations],
            projects=[ProjectSummaryResponse.model_validate(serialize_project_summary(item)) for item in projects],
            effective_scopes=effective_scopes,
        )
        total_ms = int((time.perf_counter() - started_at) * 1000)
        if AUTH_SESSION_LOG_ALL or total_ms >= AUTH_SESSION_SLOW_LOG_THRESHOLD_MS:
            logger.warning(
                "auth.session_bundle.complete total_ms=%s timings_ms=%s user_id=%s organization_id=%s project_id=%s path=%s",
                total_ms,
                timings_ms,
                str(user.id) if user is not None else None,
                str(organization.id) if organization is not None else None,
                str(project.id) if project is not None else None,
                request.url.path,
            )
        return session, bundle
    except Exception:
        total_ms = int((time.perf_counter() - started_at) * 1000)
        logger.warning(
            "auth.session_bundle.failed total_ms=%s timings_ms=%s session_id=%s user_id=%s organization_id=%s project_id=%s path=%s",
            total_ms,
            timings_ms,
            str(session.id) if session is not None else None,
            str(user.id) if user is not None else None,
            str(organization.id) if organization is not None else None,
            str(project.id) if project is not None else None,
            request.url.path,
            exc_info=True,
        )
        raise


async def _create_browser_session_response(
    *,
    request: Request,
    response: Response,
    db: AsyncSession,
    user: User,
    organization: Tenant,
    project: Project,
) -> SessionResponse:
    _session, raw_token = await BrowserSessionService(db).create_session(
        user=user,
        organization=organization,
        project=project,
    )
    _set_session_cookie(response=response, request=request, token=raw_token)
    organizations = await list_user_organizations(db=db, user_id=user.id)
    projects = await list_organization_projects(db=db, organization_id=organization.id)
    effective_scopes = await resolve_effective_scopes(
        db=db,
        user=user,
        organization_id=organization.id,
        project_id=project.id,
    )
    await db.commit()
    return SessionResponse(
        user=SessionUserResponse.model_validate(serialize_user_summary(user)),
        active_organization=OrganizationSummaryResponse.model_validate(serialize_organization_summary(organization)),
        active_project=ProjectSummaryResponse.model_validate(serialize_project_summary(project)),
        organizations=[OrganizationSummaryResponse.model_validate(serialize_organization_summary(item)) for item in organizations],
        projects=[ProjectSummaryResponse.model_validate(serialize_project_summary(item)) for item in projects],
        effective_scopes=effective_scopes,
    )


@router.post("/signup", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    existing_user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing_user is not None:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        role="user",
        avatar=f"https://api.dicebear.com/7.x/initials/svg?seed={payload.full_name or payload.email}",
    )
    db.add(user)
    await db.flush()

    owner_label = payload.full_name or payload.email.split("@", 1)[0]
    organization_slug = _slugify(owner_label, fallback=f"org-{str(user.id)[:8]}")
    organization, project = await OrganizationBootstrapService(db).create_organization_with_default_project(
        owner=user,
        name=f"{owner_label}'s Organization",
        slug=organization_slug,
    )
    return await _create_browser_session_response(
        request=request,
        response=response,
        db=db,
        user=user,
        organization=organization,
        project=project,
    )


@router.post("/register", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def register_alias(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    return await signup(payload=payload, request=request, response=response, db=db)


@router.post("/login", response_model=SessionResponse)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.email == form_data.username))).scalar_one_or_none()
    if user is None or not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    organizations = await list_user_organizations(db=db, user_id=user.id)
    if not organizations:
        raise HTTPException(status_code=403, detail="User does not belong to any organization")
    organization = organizations[0]
    projects = await list_organization_projects(db=db, organization_id=organization.id)
    if not projects:
        raise HTTPException(status_code=403, detail="Organization has no active project")
    project = projects[0]
    return await _create_browser_session_response(
        request=request,
        response=response,
        db=db,
        user=user,
        organization=organization,
        project=project,
    )


@router.post("/google", response_model=SessionResponse)
async def google_auth(
    payload: GoogleToken,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    try:
        info = id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
        if info["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
            raise ValueError("Wrong issuer")
    except Exception as exc:  # pragma: no cover - external verifier
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {exc}") from exc

    email = info["email"]
    google_id = info["sub"]
    full_name = info.get("name")
    avatar = info.get("picture")

    user = (
        await db.execute(select(User).where((User.google_id == google_id) | (User.email == email)))
    ).scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            google_id=google_id,
            full_name=full_name,
            role="user",
            avatar=avatar or f"https://api.dicebear.com/7.x/initials/svg?seed={full_name or email}",
        )
        db.add(user)
        await db.flush()
        owner_label = full_name or email.split("@", 1)[0]
        organization, project = await OrganizationBootstrapService(db).create_organization_with_default_project(
            owner=user,
            name=f"{owner_label}'s Organization",
            slug=_slugify(owner_label, fallback=f"org-{str(user.id)[:8]}"),
        )
        return await _create_browser_session_response(
            request=request,
            response=response,
            db=db,
            user=user,
            organization=organization,
            project=project,
        )

    if not user.google_id:
        user.google_id = google_id
        await db.flush()

    organizations = await list_user_organizations(db=db, user_id=user.id)
    if not organizations:
        raise HTTPException(status_code=403, detail="User does not belong to any organization")
    organization = organizations[0]
    projects = await list_organization_projects(db=db, organization_id=organization.id)
    if not projects:
        raise HTTPException(status_code=403, detail="Organization has no active project")
    project = projects[0]
    return await _create_browser_session_response(
        request=request,
        response=response,
        db=db,
        user=user,
        organization=organization,
        project=project,
    )


@router.get("/session", response_model=SessionResponse)
async def get_current_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    route_started_at = time.perf_counter()
    logger.warning(
        "auth.session.route.enter path=%s has_cookie=%s",
        request.url.path,
        bool(str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()),
    )
    _session, bundle = await _load_browser_session_bundle(request, db)
    await db.commit()
    total_ms = int((time.perf_counter() - route_started_at) * 1000)
    if AUTH_SESSION_LOG_ALL or total_ms >= AUTH_SESSION_SLOW_LOG_THRESHOLD_MS:
        logger.warning("auth.session.route.complete total_ms=%s path=%s", total_ms, request.url.path)
    return SessionResponse.model_validate(bundle.model_dump())


@router.get("/me", response_model=SessionUserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
):
    return SessionUserResponse.model_validate(serialize_user_summary(current_user))


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    raw_token = str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if raw_token:
        await BrowserSessionService(db).revoke_session(raw_token)
        await db.commit()
    _clear_session_cookie(response=response, request=request)
    return {"status": "logged_out"}


@router.post("/context/organization", response_model=SessionResponse)
async def switch_active_organization(
    payload: SwitchOrganizationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session, _bundle = await _load_browser_session_bundle(request, db)
    organizations = await list_user_organizations(db=db, user_id=session.user_id)
    organization = next((item for item in organizations if item.slug == payload.organization_slug), None)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await BrowserSessionService(db).switch_organization(session=session, organization_id=organization.id)
    await db.commit()
    _session, bundle = await _load_browser_session_bundle(request, db)
    return SessionResponse.model_validate(bundle.model_dump())


@router.post("/context/project", response_model=SessionResponse)
async def switch_active_project(
    payload: SwitchProjectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session, _bundle = await _load_browser_session_bundle(request, db)
    projects = await list_organization_projects(db=db, organization_id=session.organization_id)
    project = next((item for item in projects if item.slug == payload.project_slug), None)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await BrowserSessionService(db).switch_project(session=session, project_id=project.id)
    await db.commit()
    _session, bundle = await _load_browser_session_bundle(request, db)
    return SessionResponse.model_validate(bundle.model_dump())


@router.post("/token")
async def create_programmatic_user_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    organizations = await list_user_organizations(db=db, user_id=current_user.id)
    organization = organizations[0] if organizations else None
    access_token = create_access_token(
        subject=str(current_user.id),
        tenant_id=str(organization.id) if organization else None,
    )
    return {"access_token": access_token, "token_type": "bearer"}
