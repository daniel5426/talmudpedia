from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from workos import WorkOSClient
from workos.session import seal_session_from_auth_response

from app.db.postgres.models.identity import (
    MembershipStatus,
    OrgMembership,
    OrgRole,
    OrgUnit,
    OrgUnitType,
    Tenant,
    User,
)
from app.db.postgres.models.workspace import Project
from app.services.auth_context_service import list_organization_projects
from app.services.organization_bootstrap_service import OrganizationBootstrapService

WORKOS_SESSION_COOKIE_NAME = os.getenv("WORKOS_SESSION_COOKIE_NAME", "wos_session").strip() or "wos_session"
WORKOS_PROJECT_COOKIE_NAME = os.getenv("WORKOS_PROJECT_COOKIE_NAME", "talmudpedia_active_project").strip() or "talmudpedia_active_project"


class WorkOSAuthError(RuntimeError):
    pass


@dataclass(slots=True)
class LocalSessionBundle:
    user: User
    organization: Tenant
    project: Project
    permissions: list[str]
    workos_auth: Any


@lru_cache(maxsize=1)
def _workos_client() -> WorkOSClient:
    api_key = str(os.getenv("WORKOS_API_KEY") or "").strip()
    client_id = str(os.getenv("WORKOS_CLIENT_ID") or "").strip()
    return WorkOSClient(api_key=api_key, client_id=client_id)


def _slugify(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return cleaned[:48] or fallback


def _workos_attr(value: Any, *names: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _iter_collection(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    data = _workos_attr(value, "data")
    if isinstance(data, list):
        return data
    try:
        return list(value)
    except TypeError:
        return []


class WorkOSAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = _workos_client()

    @staticmethod
    def is_enabled() -> bool:
        required = [
            str(os.getenv("WORKOS_API_KEY") or "").strip(),
            str(os.getenv("WORKOS_CLIENT_ID") or "").strip(),
            str(os.getenv("WORKOS_COOKIE_PASSWORD") or "").strip(),
        ]
        return all(required)

    def _require_enabled(self) -> None:
        if not self.is_enabled():
            raise WorkOSAuthError("WorkOS auth is not configured")

    def _request_origin(self, request: Request) -> str:
        forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").strip()
        forwarded_host = str(request.headers.get("x-forwarded-host") or "").strip()
        if forwarded_proto and forwarded_host:
            return f"{forwarded_proto}://{forwarded_host}"
        return str(request.base_url).rstrip("/")

    def redirect_uri(self, request: Request) -> str:
        configured = str(os.getenv("WORKOS_REDIRECT_URI") or "").strip()
        if configured:
            return configured
        return f"{self._request_origin(request)}/auth/callback"

    def _request_ip(self, request: Request) -> str | None:
        forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip() or None
        client = request.client
        return getattr(client, "host", None)

    def _user_agent(self, request: Request) -> str | None:
        return str(request.headers.get("user-agent") or "").strip() or None

    def _encode_state(self, payload: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")

    def decode_state(self, state: str | None) -> dict[str, Any]:
        if not state:
            return {}
        try:
            decoded = base64.urlsafe_b64decode(state.encode("ascii")).decode("utf-8")
            data = json.loads(decoded)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def build_authorization_url(
        self,
        request: Request,
        *,
        screen_hint: str,
        return_to: str | None = None,
        organization_id: str | None = None,
        invitation_token: str | None = None,
    ) -> str:
        self._require_enabled()
        state = self._encode_state(
            {
                "return_to": return_to or "/admin/agents/playground",
                "screen_hint": screen_hint,
                "invitation_token": invitation_token,
            }
        )
        params: dict[str, Any] = {
            "provider": "authkit",
            "redirect_uri": self.redirect_uri(request),
            "state": state,
            "screen_hint": screen_hint,
        }
        if organization_id:
            params["organization_id"] = organization_id
        if invitation_token:
            params["invitation_token"] = invitation_token
        return self.client.user_management.get_authorization_url(**params)

    def current_organization_id(self, auth_response: Any) -> str | None:
        organization_id = _workos_attr(auth_response, "organization_id", "organizationId")
        return str(organization_id) if organization_id else None

    def set_session_cookie(self, *, response: Response, request: Request, sealed_session: str) -> None:
        response.set_cookie(
            key=WORKOS_SESSION_COOKIE_NAME,
            value=sealed_session,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            path="/",
        )

    def clear_session_cookie(self, *, response: Response, request: Request) -> None:
        response.delete_cookie(
            key=WORKOS_SESSION_COOKIE_NAME,
            path="/",
            secure=request.url.scheme == "https",
            samesite="lax",
        )

    def set_project_cookie(self, *, response: Response, request: Request, project_id: UUID) -> None:
        response.set_cookie(
            key=WORKOS_PROJECT_COOKIE_NAME,
            value=str(project_id),
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            path="/",
        )

    def clear_project_cookie(self, *, response: Response, request: Request) -> None:
        response.delete_cookie(
            key=WORKOS_PROJECT_COOKIE_NAME,
            path="/",
            secure=request.url.scheme == "https",
            samesite="lax",
        )

    def _load_session_helper(self, request: Request) -> Any | None:
        self._require_enabled()
        sealed_session = str(request.cookies.get(WORKOS_SESSION_COOKIE_NAME) or "").strip()
        if not sealed_session:
            return None
        return self.client.user_management.load_sealed_session(
            session_data=sealed_session,
            cookie_password=str(os.getenv("WORKOS_COOKIE_PASSWORD") or "").strip(),
        )

    def _ensure_sealed_session(self, auth_response: Any) -> Any:
        sealed_session = _workos_attr(auth_response, "sealed_session", "sealedSession")
        if sealed_session:
            return auth_response
        access_token = _workos_attr(auth_response, "access_token", "accessToken")
        refresh_token = _workos_attr(auth_response, "refresh_token", "refreshToken")
        user = _workos_attr(auth_response, "user")
        if not access_token or not refresh_token or not user:
            return auth_response
        generated = seal_session_from_auth_response(
            access_token=str(access_token),
            refresh_token=str(refresh_token),
            user=user if isinstance(user, dict) else getattr(user, "__dict__", {}),
            impersonator=_workos_attr(auth_response, "impersonator"),
            cookie_password=str(os.getenv("WORKOS_COOKIE_PASSWORD") or "").strip(),
        )
        if isinstance(auth_response, dict):
            auth_response["sealed_session"] = generated
        else:
            setattr(auth_response, "sealed_session", generated)
        return auth_response

    async def authenticate_request(self, request: Request, response: Response | None = None) -> Any | None:
        helper = self._load_session_helper(request)
        if helper is None:
            return None

        auth_response = helper.authenticate()
        if _workos_attr(auth_response, "authenticated"):
            return self._ensure_sealed_session(auth_response)

        if _workos_attr(auth_response, "reason") == "no_session_cookie_provided":
            return None

        refreshed = helper.refresh()
        if not _workos_attr(refreshed, "authenticated"):
            return None
        sealed_session = _workos_attr(refreshed, "sealed_session", "sealedSession")
        if response is not None and sealed_session:
            self.set_session_cookie(response=response, request=request, sealed_session=str(sealed_session))
        return self._ensure_sealed_session(refreshed)

    async def authenticate_with_code(
        self,
        request: Request,
        *,
        code: str,
        invitation_token: str | None = None,
    ) -> Any:
        self._require_enabled()
        body: dict[str, Any] = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": str(os.getenv("WORKOS_CLIENT_ID") or "").strip(),
            "client_secret": str(os.getenv("WORKOS_API_KEY") or "").strip(),
            "session": {
                "seal_session": True,
                "cookie_password": str(os.getenv("WORKOS_COOKIE_PASSWORD") or "").strip(),
            },
        }
        ip_address = self._request_ip(request)
        if ip_address:
            body["ip_address"] = ip_address
        user_agent = self._user_agent(request)
        if user_agent:
            body["user_agent"] = user_agent
        if invitation_token:
            body["invitation_token"] = invitation_token
        auth_response = self.client.request_raw(
            method="post",
            path="user_management/authenticate",
            body=body,
        )
        return self._ensure_sealed_session(auth_response)

    def get_logout_url(self, request: Request, *, return_to: str | None = None) -> str | None:
        helper = self._load_session_helper(request)
        if helper is None:
            return None
        return helper.get_logout_url(return_to=return_to)

    async def switch_organization(
        self,
        request: Request,
        response: Response,
        organization_id: str,
        *,
        return_to: str | None = None,
    ) -> Any:
        helper = self._load_session_helper(request)
        if helper is None:
            raise WorkOSAuthError("No active WorkOS session")
        refreshed = helper.refresh(organization_id=organization_id)
        if not _workos_attr(refreshed, "authenticated"):
            redirect_to = return_to or str(request.headers.get("referer") or "").strip() or self._request_origin(request)
            return {
                "redirect_url": self.build_authorization_url(
                    request,
                    screen_hint="sign-in",
                    return_to=redirect_to,
                    organization_id=organization_id,
                )
            }
        sealed_session = _workos_attr(refreshed, "sealed_session", "sealedSession")
        if sealed_session:
            self.set_session_cookie(response=response, request=request, sealed_session=str(sealed_session))
        return refreshed

    async def sync_local_user(self, auth_response: Any) -> User:
        workos_user = _workos_attr(auth_response, "user")
        if workos_user is None:
            raise WorkOSAuthError("WorkOS auth response is missing a user")
        return await self._upsert_local_user(workos_user)

    async def sync_current_organization(
        self,
        *,
        auth_response: Any,
        actor_user_id: UUID | None = None,
    ) -> Tenant | None:
        local_user = await self.sync_local_user(auth_response)
        workos_org_id = self.current_organization_id(auth_response)
        if not workos_org_id:
            return None
        local_org = await self._sync_local_organization_from_workos(
            workos_org_id,
            actor_user_id=actor_user_id or local_user.id,
            create_if_missing=True,
        )
        membership = _workos_attr(auth_response, "organization_membership", "organizationMembership")
        if membership is None and local_user.workos_user_id:
            memberships = self.client.user_management.list_organization_memberships(
                user_id=local_user.workos_user_id,
                organization_id=workos_org_id,
            )
            items = _iter_collection(memberships)
            membership = items[0] if items else None
        if membership is not None:
            await self._upsert_local_membership(local_user, local_org, membership)
        return local_org

    async def ensure_local_bundle(
        self,
        *,
        auth_response: Any,
        request: Request | None = None,
        actor_user_id: UUID | None = None,
    ) -> LocalSessionBundle:
        local_user = await self.sync_local_user(auth_response)
        workos_org_id = self.current_organization_id(auth_response)
        if not workos_org_id:
            raise WorkOSAuthError("Authenticated WorkOS session does not include an organization")

        del actor_user_id
        local_org = await self._read_local_organization(workos_org_id)
        if local_org is None:
            raise WorkOSAuthError("Local organization mirror is missing for current WorkOS organization")

        project = await self._resolve_active_project(request=request, organization=local_org)
        permissions = self._extract_permissions(auth_response)
        await self.db.flush()
        return LocalSessionBundle(
            user=local_user,
            organization=local_org,
            project=project,
            permissions=permissions,
            workos_auth=auth_response,
        )

    def _extract_permissions(self, auth_response: Any) -> list[str]:
        permissions: list[str] = []
        for item in _iter_collection(_workos_attr(auth_response, "permissions")):
            if isinstance(item, str):
                permissions.append(item)
                continue
            slug = _workos_attr(item, "slug", "name", "permission")
            if slug:
                permissions.append(str(slug))
        return sorted({permission for permission in permissions if permission})

    def _workos_role_slug(self) -> str | None:
        value = str(os.getenv("WORKOS_ORGANIZATION_ROLE_SLUG") or "").strip()
        return value or None

    def _create_workos_membership(self, *, user_id: str, organization_id: str) -> Any:
        existing_memberships = self.client.user_management.list_organization_memberships(
            user_id=user_id,
            organization_id=organization_id,
        )
        existing_items = _iter_collection(existing_memberships)
        if existing_items:
            return existing_items[0]
        params: dict[str, Any] = {
            "user_id": user_id,
            "organization_id": organization_id,
        }
        role_slug = self._workos_role_slug()
        if role_slug:
            params["role_slug"] = role_slug
        return self.client.user_management.create_organization_membership(**params)

    async def _upsert_local_user(self, workos_user: Any) -> User:
        workos_user_id = str(_workos_attr(workos_user, "id"))
        email = str(_workos_attr(workos_user, "email") or "").strip().lower()
        if not workos_user_id or not email:
            raise WorkOSAuthError("WorkOS user is missing id or email")

        result = await self.db.execute(
            select(User).where((User.workos_user_id == workos_user_id) | (User.email == email))
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(email=email, role="user")
            self.db.add(user)
        user.workos_user_id = workos_user_id
        user.email = email
        user.full_name = _workos_attr(workos_user, "first_name", "firstName") and (
            f"{_workos_attr(workos_user, 'first_name', 'firstName')} {_workos_attr(workos_user, 'last_name', 'lastName') or ''}".strip()
        ) or _workos_attr(workos_user, "full_name", "fullName") or user.full_name
        user.avatar = _workos_attr(workos_user, "profile_picture_url", "profilePictureUrl", "avatar_url") or user.avatar
        await self.db.flush()
        return user

    async def _ensure_root_org_unit(self, organization: Tenant) -> OrgUnit:
        result = await self.db.execute(
            select(OrgUnit).where(OrgUnit.tenant_id == organization.id).order_by(OrgUnit.created_at.asc()).limit(1)
        )
        root = result.scalar_one_or_none()
        if root is not None:
            return root
        root = OrgUnit(
            tenant_id=organization.id,
            name=organization.name,
            slug="root",
            type=OrgUnitType.org,
        )
        self.db.add(root)
        await self.db.flush()
        return root

    async def _unique_org_slug(self, desired: str) -> str:
        base = _slugify(desired, fallback="organization")
        slug = base
        suffix = 1
        while True:
            existing = (await self.db.execute(select(Tenant.id).where(Tenant.slug == slug))).scalar_one_or_none()
            if existing is None:
                return slug
            suffix += 1
            slug = f"{base[:42]}-{suffix}"

    async def _read_local_organization(self, workos_organization_id: str) -> Tenant | None:
        result = await self.db.execute(select(Tenant).where(Tenant.workos_organization_id == workos_organization_id))
        return result.scalar_one_or_none()

    async def _sync_local_organization_from_workos(
        self,
        workos_organization_id: str,
        *,
        actor_user_id: UUID | None,
        create_if_missing: bool,
    ) -> Tenant:
        organization = await self._read_local_organization(workos_organization_id)
        workos_org = self.client.organizations.get_organization(workos_organization_id)
        name = str(_workos_attr(workos_org, "name") or "Organization").strip() or "Organization"

        if organization is None:
            if not create_if_missing:
                raise WorkOSAuthError("Local organization mirror is missing for current WorkOS organization")
            if actor_user_id is None:
                raise WorkOSAuthError("Owner user not found for organization provisioning")
            owner = await self.db.get(User, actor_user_id)
            if owner is None:
                raise WorkOSAuthError("Owner user not found for organization provisioning")
            slug = await self._unique_org_slug(str(_workos_attr(workos_org, "slug") or name))
            organization, _ = await OrganizationBootstrapService(self.db).create_organization_with_default_project(
                owner=owner,
                name=name,
                slug=slug,
                workos_organization_id=workos_organization_id,
            )
        else:
            organization.name = name
            organization.workos_organization_id = workos_organization_id
            await self._ensure_root_org_unit(organization)
        await self.db.flush()
        return organization

    async def _upsert_local_membership(self, local_user: User, local_org: Tenant, workos_membership: Any) -> OrgMembership:
        root = await self._ensure_root_org_unit(local_org)
        workos_membership_id = _workos_attr(workos_membership, "id")
        result = await self.db.execute(
            select(OrgMembership).where(
                (OrgMembership.workos_membership_id == workos_membership_id)
                | ((OrgMembership.tenant_id == local_org.id) & (OrgMembership.user_id == local_user.id))
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            membership = OrgMembership(
                tenant_id=local_org.id,
                user_id=local_user.id,
                org_unit_id=root.id,
            )
            self.db.add(membership)
        membership.org_unit_id = root.id
        membership.workos_membership_id = str(workos_membership_id) if workos_membership_id else membership.workos_membership_id
        membership.status = self._map_membership_status(_workos_attr(workos_membership, "status"))
        membership.role = self._map_membership_role(_workos_attr(workos_membership, "role_slug", "roleSlug", "role"))
        await self.db.flush()
        return membership

    def _map_membership_status(self, value: Any) -> MembershipStatus:
        normalized = str(value or "active").strip().lower()
        if normalized == "inactive":
            return MembershipStatus.suspended
        if normalized in {"active", "pending", "invited", "suspended"}:
            return MembershipStatus(normalized)
        return MembershipStatus.active

    def _map_membership_role(self, value: Any) -> OrgRole:
        normalized = str(value or "member").strip().lower()
        if "owner" in normalized:
            return OrgRole.owner
        if "admin" in normalized:
            return OrgRole.admin
        return OrgRole.member

    async def _sync_user_memberships(self, local_user: User) -> None:
        if not local_user.workos_user_id:
            return
        memberships = self.client.user_management.list_organization_memberships(user_id=local_user.workos_user_id)
        for workos_membership in _iter_collection(memberships):
            workos_org_id = _workos_attr(workos_membership, "organization_id", "organizationId")
            if not workos_org_id:
                continue
            local_org = await self._sync_local_organization_from_workos(
                str(workos_org_id),
                actor_user_id=local_user.id,
                create_if_missing=True,
            )
            await self._upsert_local_membership(local_user, local_org, workos_membership)
        await self.db.flush()

    async def sync_workos_user_by_id(self, workos_user_id: str) -> User:
        workos_user = self.client.user_management.get_user(workos_user_id)
        return await self._upsert_local_user(workos_user)

    async def sync_workos_membership(
        self,
        *,
        workos_user_id: str,
        workos_organization_id: str,
        create_org_if_missing: bool = True,
    ) -> OrgMembership | None:
        local_user = await self.sync_workos_user_by_id(workos_user_id)
        local_org = await self._sync_local_organization_from_workos(
            workos_organization_id,
            actor_user_id=local_user.id,
            create_if_missing=create_org_if_missing,
        )
        memberships = self.client.user_management.list_organization_memberships(
            user_id=workos_user_id,
            organization_id=workos_organization_id,
        )
        items = _iter_collection(memberships)
        if not items:
            return None
        return await self._upsert_local_membership(local_user, local_org, items[0])

    async def sync_workos_organization_by_id(
        self,
        *,
        workos_organization_id: str,
        actor_user_id: UUID | None = None,
        create_if_missing: bool = False,
    ) -> Tenant | None:
        try:
            return await self._sync_local_organization_from_workos(
                workos_organization_id,
                actor_user_id=actor_user_id,
                create_if_missing=create_if_missing,
            )
        except WorkOSAuthError:
            if create_if_missing:
                raise
            return None

    async def _ensure_default_project(self, organization: Tenant, actor_user_id: UUID | None) -> Project:
        projects = await list_organization_projects(db=self.db, organization_id=organization.id)
        for project in projects:
            if project.is_default:
                return project
        service = OrganizationBootstrapService(self.db)
        return await service.create_project(
            organization=organization,
            created_by=actor_user_id,
            name="Default Project",
            slug="default",
            is_default=True,
            owner_user_id=actor_user_id,
        )

    async def _resolve_active_project(self, *, request: Request | None, organization: Tenant) -> Project:
        requested_project_id = None
        if request is not None:
            requested_project_id = str(request.cookies.get(WORKOS_PROJECT_COOKIE_NAME) or "").strip()
        if requested_project_id:
            try:
                project = await self.db.get(Project, UUID(requested_project_id))
                if project is not None and project.organization_id == organization.id:
                    return project
            except ValueError:
                pass
        projects = await list_organization_projects(db=self.db, organization_id=organization.id)
        for project in projects:
            if project.is_default:
                return project
        return await self._ensure_default_project(organization, None)

    async def create_organization_for_user(
        self,
        *,
        local_user: User,
        name: str,
        slug: str,
        request: Request,
        response: Response,
        return_to: str | None = None,
    ) -> LocalSessionBundle | dict[str, str]:
        self._require_enabled()
        if not local_user.workos_user_id:
            raise WorkOSAuthError("Current user is not linked to WorkOS")
        workos_org = self.client.organizations.create_organization(name=name, external_id=slug)
        workos_membership = self._create_workos_membership(
            user_id=local_user.workos_user_id,
            organization_id=str(_workos_attr(workos_org, "id")),
        )
        organization, project = await OrganizationBootstrapService(self.db).create_organization_with_default_project(
            owner=local_user,
            name=name,
            slug=slug,
            workos_organization_id=str(_workos_attr(workos_org, "id")),
            workos_membership_id=str(_workos_attr(workos_membership, "id")),
        )
        switched = await self.switch_organization(
            request,
            response,
            str(_workos_attr(workos_org, "id")),
            return_to=return_to,
        )
        if isinstance(switched, dict):
            return switched
        await self._upsert_local_membership(local_user, organization, workos_membership)
        self.set_project_cookie(response=response, request=request, project_id=project.id)
        return LocalSessionBundle(
            user=local_user,
            organization=organization,
            project=project,
            permissions=self._extract_permissions(switched),
            workos_auth=switched,
        )

    def verify_webhook_signature(self, *, payload: bytes, sig_header: str) -> None:
        secret = str(os.getenv("WORKOS_WEBHOOK_SECRET") or "").strip()
        if not secret:
            raise WorkOSAuthError("WORKOS_WEBHOOK_SECRET is not configured")
        header_parts = [part.strip() for part in sig_header.split(",") if part.strip()]
        issued_timestamp = None
        provided_signature = None
        for part in header_parts:
            if part.startswith("t="):
                issued_timestamp = part[2:]
            elif part.startswith("v1="):
                provided_signature = part[3:]
        if not issued_timestamp or not provided_signature:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WorkOS signature header")
        signed_payload = f"{issued_timestamp}.{payload.decode('utf-8')}".encode("utf-8")
        expected_signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_signature, provided_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WorkOS webhook signature")
