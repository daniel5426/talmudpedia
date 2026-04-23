from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from workos import WorkOSClient

from app.db.postgres.models.identity import (
    MembershipStatus,
    OrgInvite,
    OrgMembership,
    OrgUnit,
    OrgUnitType,
    Organization,
    User,
)
from app.db.postgres.models.rbac import Role, RoleAssignment
from app.db.postgres.models.workspace import Project
from app.services.auth_context_service import list_organization_projects, list_user_organizations
from app.services.organization_bootstrap_service import OrganizationBootstrapService
from app.services.security_bootstrap_service import SecurityBootstrapService

logger = logging.getLogger(__name__)

WORKOS_SESSION_COOKIE_NAME = os.getenv("WORKOS_SESSION_COOKIE_NAME", "wos_session").strip() or "wos_session"
WORKOS_PROJECT_COOKIE_NAME = os.getenv("WORKOS_PROJECT_COOKIE_NAME", "talmudpedia_active_project").strip() or "talmudpedia_active_project"
WORKOS_AUTH_DEBUG_LOG_PATH = (
    os.getenv("WORKOS_AUTH_DEBUG_LOG_PATH", "/tmp/talmudpedia-workos-auth.jsonl").strip()
    or "/tmp/talmudpedia-workos-auth.jsonl"
)


class WorkOSAuthError(RuntimeError):
    pass


@dataclass(slots=True)
class LocalSessionBundle:
    user: User
    organization: Organization
    project: Project
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
    _refresh_flights: dict[str, asyncio.Future[Any]] = {}
    _refresh_flights_guard: asyncio.Lock | None = None

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = _workos_client()

    @staticmethod
    def _fingerprint_secret(value: str | None) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _auth_debug_log(
        self,
        event: str,
        *,
        request: Request | None = None,
        fields: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "pid": os.getpid(),
            "workos_client_id_fp": self._fingerprint_secret(os.getenv("WORKOS_CLIENT_ID")),
            "workos_cookie_password_fp": self._fingerprint_secret(os.getenv("WORKOS_COOKIE_PASSWORD")),
        }
        if request is not None:
            cookie_value = str(request.cookies.get(WORKOS_SESSION_COOKIE_NAME) or "").strip()
            payload.update(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "query": request.url.query,
                    "host": str(request.headers.get("host") or "").strip(),
                    "origin": str(request.headers.get("origin") or "").strip(),
                    "referer": str(request.headers.get("referer") or "").strip(),
                    "user_agent": str(request.headers.get("user-agent") or "").strip()[:240],
                    "cookie_present": bool(cookie_value),
                    "cookie_fp": self._fingerprint_secret(cookie_value),
                }
            )
        if fields:
            payload.update(fields)
        try:
            path = Path(WORKOS_AUTH_DEBUG_LOG_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")
        except Exception:
            logger.exception("Failed to write WorkOS auth debug log")

    @classmethod
    def _get_refresh_flights_guard(cls) -> asyncio.Lock:
        if cls._refresh_flights_guard is None:
            cls._refresh_flights_guard = asyncio.Lock()
        return cls._refresh_flights_guard

    async def _get_or_create_refresh_flight(self, key: str) -> tuple[asyncio.Future[Any], bool]:
        guard = self._get_refresh_flights_guard()
        async with guard:
            future = self._refresh_flights.get(key)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                self._refresh_flights[key] = future
                return future, True
            return future, False

    async def _finish_refresh_flight(self, key: str, future: asyncio.Future[Any]) -> None:
        guard = self._get_refresh_flights_guard()
        async with guard:
            current = self._refresh_flights.get(key)
            if current is future:
                self._refresh_flights.pop(key, None)

    async def _refresh_session_helper(self, helper: Any) -> Any:
        return await asyncio.to_thread(helper.refresh)

    async def _refresh_with_single_flight(self, *, request: Request, helper: Any) -> Any:
        cookie_value = str(request.cookies.get(WORKOS_SESSION_COOKIE_NAME) or "").strip()
        refresh_key = self._fingerprint_secret(cookie_value) or "missing"
        future, is_leader = await self._get_or_create_refresh_flight(refresh_key)
        if is_leader:
            self._auth_debug_log(
                "authenticate_request.refresh_single_flight_leader",
                request=request,
                fields={"refresh_cookie_fp": refresh_key},
            )
            try:
                refreshed = await self._refresh_session_helper(helper)
                if not future.done():
                    future.set_result(refreshed)
                return refreshed
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
                raise
            finally:
                await self._finish_refresh_flight(refresh_key, future)

        self._auth_debug_log(
            "authenticate_request.refresh_single_flight_wait",
            request=request,
            fields={"refresh_cookie_fp": refresh_key},
        )
        return await future

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
            self._auth_debug_log("load_session_helper.missing_cookie", request=request)
            return None
        try:
            cookie_password = str(os.getenv("WORKOS_COOKIE_PASSWORD") or "").strip()
            try:
                helper = self.client.user_management.load_sealed_session(
                    sealed_session=sealed_session,
                    cookie_password=cookie_password,
                )
            except TypeError:
                helper = self.client.user_management.load_sealed_session(
                    session_data=sealed_session,
                    cookie_password=cookie_password,
                )
            self._auth_debug_log("load_session_helper.loaded", request=request)
            return helper
        except Exception as exc:
            self._auth_debug_log(
                "load_session_helper.failed",
                request=request,
                fields={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

    async def authenticate_request(self, request: Request, response: Response | None = None) -> Any | None:
        try:
            helper = self._load_session_helper(request)
            if helper is None:
                self._auth_debug_log("authenticate_request.no_helper", request=request)
                return None

            auth_response = helper.authenticate()
            authenticated = bool(_workos_attr(auth_response, "authenticated"))
            reason = _workos_attr(auth_response, "reason")
            self._auth_debug_log(
                "authenticate_request.authenticate_result",
                request=request,
                fields={
                    "authenticated": authenticated,
                    "reason": reason,
                },
            )
            if authenticated:
                return auth_response

            if reason == "no_session_cookie_provided":
                return None

            refreshed = await self._refresh_with_single_flight(request=request, helper=helper)
            refresh_authenticated = bool(_workos_attr(refreshed, "authenticated"))
            refresh_reason = _workos_attr(refreshed, "reason")
            self._auth_debug_log(
                "authenticate_request.refresh_result",
                request=request,
                fields={
                    "authenticated": refresh_authenticated,
                    "reason": refresh_reason,
                },
            )
            if not refresh_authenticated:
                return None
            sealed_session = _workos_attr(refreshed, "sealed_session", "sealedSession")
            if response is not None and sealed_session:
                self.set_session_cookie(response=response, request=request, sealed_session=str(sealed_session))
                self._auth_debug_log(
                    "authenticate_request.session_cookie_refreshed",
                    request=request,
                    fields={
                        "refreshed_cookie_fp": self._fingerprint_secret(str(sealed_session)),
                    },
                )
            return refreshed
        except Exception as exc:
            self._auth_debug_log(
                "authenticate_request.exception",
                request=request,
                fields={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

    async def authenticate_with_code(
        self,
        request: Request,
        *,
        code: str,
        invitation_token: str | None = None,
    ) -> Any:
        self._require_enabled()
        auth_response = self.client.user_management.authenticate_with_code(
            code=code,
            session={
                "seal_session": True,
                "cookie_password": str(os.getenv("WORKOS_COOKIE_PASSWORD") or "").strip(),
            },
            ip_address=self._request_ip(request),
            user_agent=self._user_agent(request),
            invitation_token=invitation_token,
        )
        return auth_response

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
    ) -> Organization | None:
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
        await self.db.flush()
        return LocalSessionBundle(
            user=local_user,
            organization=local_org,
            project=project,
            workos_auth=auth_response,
        )

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

    async def _ensure_root_org_unit(self, organization: Organization) -> OrgUnit:
        result = await self.db.execute(
            select(OrgUnit).where(OrgUnit.organization_id == organization.id).order_by(OrgUnit.created_at.asc()).limit(1)
        )
        root = result.scalar_one_or_none()
        if root is not None:
            return root
        root = OrgUnit(
            organization_id=organization.id,
            name=organization.name,
            slug="root",
            system_key="root",
            type=OrgUnitType.org,
        )
        self.db.add(root)
        await self.db.flush()
        return root

    async def _read_local_organization(self, workos_organization_id: str) -> Organization | None:
        result = await self.db.execute(select(Organization).where(Organization.workos_organization_id == workos_organization_id))
        return result.scalar_one_or_none()

    async def _sync_local_organization_from_workos(
        self,
        workos_organization_id: str,
        *,
        actor_user_id: UUID | None,
        create_if_missing: bool,
    ) -> Organization:
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
            organization, _ = await OrganizationBootstrapService(self.db).create_organization_with_default_project(
                owner=owner,
                name=name,
                workos_organization_id=workos_organization_id,
            )
        else:
            organization.name = name
            organization.workos_organization_id = workos_organization_id
            await self._ensure_root_org_unit(organization)
        await self.db.flush()
        return organization

    async def _upsert_local_membership(self, local_user: User, local_org: Organization, workos_membership: Any) -> OrgMembership:
        root = await self._ensure_root_org_unit(local_org)
        workos_membership_id = _workos_attr(workos_membership, "id")
        result = await self.db.execute(
            select(OrgMembership).where(
                (OrgMembership.workos_membership_id == workos_membership_id)
                | ((OrgMembership.organization_id == local_org.id) & (OrgMembership.user_id == local_user.id))
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            membership = OrgMembership(
                organization_id=local_org.id,
                user_id=local_user.id,
                org_unit_id=root.id,
            )
            self.db.add(membership)
        membership.org_unit_id = root.id
        membership.workos_membership_id = str(workos_membership_id) if workos_membership_id else membership.workos_membership_id
        membership.status = self._map_membership_status(_workos_attr(workos_membership, "status"))
        bootstrap = SecurityBootstrapService(self.db)
        has_org_assignment = (
            await self.db.execute(
                select(RoleAssignment.id)
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(
                    RoleAssignment.organization_id == local_org.id,
                    RoleAssignment.user_id == local_user.id,
                    RoleAssignment.project_id.is_(None),
                    Role.family == "organization",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if membership.status == MembershipStatus.active and has_org_assignment is None:
            await bootstrap.ensure_organization_reader_assignment(
                organization_id=local_org.id,
                user_id=local_user.id,
                assigned_by=local_user.id,
            )
        pending_invites = (
            await self.db.execute(
                select(OrgInvite).where(
                    OrgInvite.organization_id == local_org.id,
                    OrgInvite.email == local_user.email,
                    OrgInvite.accepted_at.is_(None),
                )
            )
        ).scalars().all()
        for invite in pending_invites:
            for project_id in invite.project_ids or []:
                try:
                    if invite.project_role_id:
                        await bootstrap.ensure_project_role_assignment(
                            organization_id=local_org.id,
                            project_id=UUID(str(project_id)),
                            user_id=local_user.id,
                            role_id=invite.project_role_id,
                            assigned_by=local_user.id,
                        )
                    else:
                        await bootstrap.ensure_project_member_assignment(
                            organization_id=local_org.id,
                            project_id=UUID(str(project_id)),
                            user_id=local_user.id,
                            assigned_by=local_user.id,
                        )
                except Exception:
                    continue
            invite.accepted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return membership

    async def _remove_local_membership(self, *, membership: OrgMembership) -> None:
        await self.db.execute(
            delete(RoleAssignment).where(
                RoleAssignment.organization_id == membership.organization_id,
                RoleAssignment.user_id == membership.user_id,
            )
        )
        await self.db.delete(membership)
        await self.db.flush()

    def _map_membership_status(self, value: Any) -> MembershipStatus:
        normalized = str(value or "active").strip().lower()
        if normalized == "inactive":
            return MembershipStatus.suspended
        if normalized in {"active", "pending", "invited", "suspended"}:
            return MembershipStatus(normalized)
        return MembershipStatus.active

    async def _sync_user_memberships(self, local_user: User) -> None:
        if not local_user.workos_user_id:
            return
        memberships = self.client.user_management.list_organization_memberships(user_id=local_user.workos_user_id)
        membership_items = _iter_collection(memberships)
        seen_membership_ids: set[str] = set()
        seen_workos_org_ids: set[str] = set()
        for workos_membership in membership_items:
            workos_org_id = _workos_attr(workos_membership, "organization_id", "organizationId")
            if not workos_org_id:
                continue
            membership_id = _workos_attr(workos_membership, "id")
            if membership_id:
                seen_membership_ids.add(str(membership_id))
            seen_workos_org_ids.add(str(workos_org_id))
            local_org = await self._sync_local_organization_from_workos(
                str(workos_org_id),
                actor_user_id=local_user.id,
                create_if_missing=True,
            )
            await self._upsert_local_membership(local_user, local_org, workos_membership)

        local_memberships = (
            await self.db.execute(
                select(OrgMembership, Organization)
                .join(Organization, Organization.id == OrgMembership.organization_id)
                .where(
                    OrgMembership.user_id == local_user.id,
                    Organization.workos_organization_id.is_not(None),
                )
            )
        ).all()
        for membership, organization in local_memberships:
            workos_membership_id = str(membership.workos_membership_id or "").strip()
            workos_org_id = str(organization.workos_organization_id or "").strip()
            if workos_membership_id and workos_membership_id in seen_membership_ids:
                continue
            if workos_org_id and workos_org_id in seen_workos_org_ids:
                continue
            await self._remove_local_membership(membership=membership)
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
            membership = (
                await self.db.execute(
                    select(OrgMembership).where(
                        OrgMembership.organization_id == local_org.id,
                        OrgMembership.user_id == local_user.id,
                    )
                )
            ).scalar_one_or_none()
            if membership is not None:
                await self._remove_local_membership(membership=membership)
            return None
        return await self._upsert_local_membership(local_user, local_org, items[0])

    async def remove_workos_membership(
        self,
        *,
        workos_user_id: str,
        workos_organization_id: str,
    ) -> None:
        local_org = await self._read_local_organization(workos_organization_id)
        if local_org is None:
            return
        local_user = (
            await self.db.execute(select(User).where(User.workos_user_id == workos_user_id).limit(1))
        ).scalar_one_or_none()
        if local_user is None:
            return
        memberships = (
            await self.db.execute(
                select(OrgMembership).where(
                    OrgMembership.organization_id == local_org.id,
                    OrgMembership.user_id == local_user.id,
                )
            )
        ).scalars().all()
        for membership in memberships:
            await self._remove_local_membership(membership=membership)

    async def sync_workos_organization_by_id(
        self,
        *,
        workos_organization_id: str,
        actor_user_id: UUID | None = None,
        create_if_missing: bool = False,
    ) -> Organization | None:
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

    async def _ensure_default_project(self, organization: Organization, actor_user_id: UUID | None) -> Project:
        projects = await list_organization_projects(db=self.db, organization_id=organization.id)
        for project in projects:
            if project.is_default:
                return project
        service = OrganizationBootstrapService(self.db)
        return await service.create_project(
            organization=organization,
            created_by=actor_user_id,
            name="Default Project",
            is_default=True,
            owner_user_id=actor_user_id,
        )

    async def _resolve_active_project(self, *, request: Request | None, organization: Organization) -> Project:
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

    async def recover_no_active_organization(
        self,
        *,
        auth_response: Any,
        request: Request,
        response: Response,
        return_to: str | None = None,
    ) -> LocalSessionBundle | dict[str, str] | None:
        local_user = await self.sync_local_user(auth_response)
        await self._sync_user_memberships(local_user)
        organizations = await list_user_organizations(db=self.db, user_id=local_user.id)
        if not organizations:
            return None

        if len(organizations) == 1:
            organization = organizations[0]
            if not organization.workos_organization_id:
                return None
            switched = await self.switch_organization(
                request,
                response,
                organization.workos_organization_id,
                return_to=return_to,
            )
            if isinstance(switched, dict):
                return switched
            await self.sync_current_organization(auth_response=switched, actor_user_id=local_user.id)
            bundle = await self.ensure_local_bundle(
                auth_response=switched,
                request=request,
                actor_user_id=local_user.id,
            )
            self.set_project_cookie(response=response, request=request, project_id=bundle.project.id)
            return bundle

        redirect_to = return_to or str(request.headers.get("referer") or "").strip() or self._request_origin(request)
        return {
            "redirect_url": self.build_authorization_url(
                request,
                screen_hint="sign-in",
                return_to=redirect_to,
            )
        }

    async def create_organization_for_user(
        self,
        *,
        local_user: User,
        name: str,
        request: Request,
        response: Response,
        return_to: str | None = None,
    ) -> LocalSessionBundle | dict[str, str]:
        self._require_enabled()
        if not local_user.workos_user_id:
            raise WorkOSAuthError("Current user is not linked to WorkOS")
        workos_org = self.client.organizations.create_organization(name=name, external_id=f"organization_{uuid4().hex}")
        workos_membership = self._create_workos_membership(
            user_id=local_user.workos_user_id,
            organization_id=str(_workos_attr(workos_org, "id")),
        )
        organization, project = await OrganizationBootstrapService(self.db).create_organization_with_default_project(
            owner=local_user,
            name=name,
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
