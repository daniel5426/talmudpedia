import asyncio
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Response
from sqlalchemy import select
from starlette.requests import Request

from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.rbac import RoleAssignment
from app.services.workos_auth_service import WorkOSAuthService
from app.services.security_bootstrap_service import SecurityBootstrapService


def _request_with_session_cookie(value: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/session",
            "query_string": b"",
            "scheme": "http",
            "headers": [
                (b"host", b"localhost:8026"),
                (b"origin", b"http://localhost:3000"),
                (b"referer", b"http://localhost:3000/"),
                (b"cookie", f"wos_session={value}".encode("utf-8")),
            ],
            "server": ("localhost", 8026),
            "client": ("127.0.0.1", 12345),
        }
    )


def _request_without_session_cookie() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/callback",
            "query_string": b"",
            "scheme": "http",
            "headers": [
                (b"host", b"localhost:8026"),
                (b"origin", b"http://localhost:3000"),
                (b"referer", b"http://localhost:3000/"),
            ],
            "server": ("localhost", 8026),
            "client": ("127.0.0.1", 12345),
        }
    )


@pytest.mark.asyncio
async def test_authenticate_request_uses_native_session_refresh(monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", "test-cookie-password")

    calls: dict[str, object] = {}

    class FakeSessionHelper:
        def authenticate(self):
            calls["authenticate_called"] = True
            return SimpleNamespace(authenticated=False, reason="invalid_jwt")

        def refresh(self):
            calls["refresh_called"] = True
            return SimpleNamespace(authenticated=True, reason=None, sealed_session="rotated-session")

    class FakeUserManagement:
        def load_sealed_session(self, *, sealed_session, cookie_password):
            calls["load_sealed_session"] = {
                "sealed_session": sealed_session,
                "cookie_password": cookie_password,
            }
            return FakeSessionHelper()

    fake_client = SimpleNamespace(user_management=FakeUserManagement())
    monkeypatch.setattr("app.services.workos_auth_service._workos_client", lambda: fake_client)

    service = WorkOSAuthService(db=None)
    request = _request_with_session_cookie("stale-session")
    response = Response()

    refreshed = await service.authenticate_request(request, response)

    assert refreshed.authenticated is True
    assert calls["load_sealed_session"] == {
        "sealed_session": "stale-session",
        "cookie_password": "test-cookie-password",
    }
    assert calls["authenticate_called"] is True
    assert calls["refresh_called"] is True
    assert "wos_session=rotated-session" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_authenticate_with_code_uses_native_workos_helper(monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", "test-cookie-password")

    calls: dict[str, object] = {}

    class FakeUserManagement:
        def authenticate_with_code(
            self,
            *,
            code,
            session,
            ip_address=None,
            user_agent=None,
            invitation_token=None,
        ):
            calls["authenticate_with_code"] = {
                "code": code,
                "session": session,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "invitation_token": invitation_token,
            }
            return SimpleNamespace(
                sealed_session="fresh-session",
                user={"id": "user_123"},
                organization_id="org_123",
            )

    fake_client = SimpleNamespace(user_management=FakeUserManagement())
    monkeypatch.setattr("app.services.workos_auth_service._workos_client", lambda: fake_client)

    service = WorkOSAuthService(db=None)
    request = _request_with_session_cookie("old-session")

    auth_response = await service.authenticate_with_code(
        request,
        code="code_123",
        invitation_token="invite_123",
    )

    assert auth_response.sealed_session == "fresh-session"
    assert calls["authenticate_with_code"] == {
        "code": "code_123",
        "session": {
            "seal_session": True,
            "cookie_password": "test-cookie-password",
        },
        "ip_address": "127.0.0.1",
        "user_agent": None,
        "invitation_token": "invite_123",
    }


@pytest.mark.asyncio
async def test_switch_organization_can_use_callback_sealed_session(monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", "test-cookie-password")

    calls: dict[str, object] = {}

    class FakeSessionHelper:
        def refresh(self, *, organization_id):
            calls["refresh_organization_id"] = organization_id
            return SimpleNamespace(authenticated=True, reason=None, sealed_session="org-session")

    class FakeUserManagement:
        def load_sealed_session(self, *, sealed_session, cookie_password):
            calls["load_sealed_session"] = {
                "sealed_session": sealed_session,
                "cookie_password": cookie_password,
            }
            return FakeSessionHelper()

    fake_client = SimpleNamespace(user_management=FakeUserManagement())
    monkeypatch.setattr("app.services.workos_auth_service._workos_client", lambda: fake_client)

    service = WorkOSAuthService(db=None)
    request = _request_without_session_cookie()
    response = Response()

    switched = await service.switch_organization(
        request,
        response,
        "org_123",
        sealed_session="callback-session",
    )

    assert switched.authenticated is True
    assert calls["load_sealed_session"] == {
        "sealed_session": "callback-session",
        "cookie_password": "test-cookie-password",
    }
    assert calls["refresh_organization_id"] == "org_123"
    assert "wos_session=org-session" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_authenticate_request_coalesces_concurrent_refresh(monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", "test-cookie-password")

    calls: dict[str, int] = {"refresh_count": 0}

    class FakeSessionHelper:
        def authenticate(self):
            return SimpleNamespace(authenticated=False, reason="invalid_jwt")

        def refresh(self):
            calls["refresh_count"] += 1
            time.sleep(0.05)
            return SimpleNamespace(authenticated=True, reason=None, sealed_session="rotated-session")

    class FakeUserManagement:
        def load_sealed_session(self, *, sealed_session, cookie_password):
            assert sealed_session == "stale-session"
            assert cookie_password == "test-cookie-password"
            return FakeSessionHelper()

    fake_client = SimpleNamespace(user_management=FakeUserManagement())
    monkeypatch.setattr("app.services.workos_auth_service._workos_client", lambda: fake_client)

    service = WorkOSAuthService(db=None)
    request_a = _request_with_session_cookie("stale-session")
    request_b = _request_with_session_cookie("stale-session")
    response_a = Response()
    response_b = Response()

    refreshed_a, refreshed_b = await asyncio.gather(
        service.authenticate_request(request_a, response_a),
        service.authenticate_request(request_b, response_b),
    )

    assert calls["refresh_count"] == 1
    assert refreshed_a.authenticated is True
    assert refreshed_b.authenticated is True
    assert "wos_session=rotated-session" in response_a.headers["set-cookie"]
    assert "wos_session=rotated-session" in response_b.headers["set-cookie"]


@pytest.mark.asyncio
async def test_remove_workos_membership_revokes_local_access(db_session, monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    tenant = Organization(
        name=f"Organization {uuid4().hex[:6]}",
        slug=f"tenant-{uuid4().hex[:8]}",
        workos_organization_id=f"wos_org_{uuid4().hex[:8]}",
    )
    user = User(
        email=f"user-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="user",
        workos_user_id=f"wos_user_{uuid4().hex[:8]}",
    )
    db_session.add_all([tenant, user])
    await db_session.flush()

    root = OrgUnit(organization_id=tenant.id, name="Root", slug=f"root-{uuid4().hex[:6]}", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    membership = OrgMembership(
        organization_id=tenant.id,
        user_id=user.id,
        org_unit_id=root.id,
        status=MembershipStatus.active,
    )
    db_session.add(membership)
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_reader_assignment(
        organization_id=tenant.id,
        user_id=user.id,
        assigned_by=user.id,
    )
    await db_session.commit()

    service = WorkOSAuthService(db_session)
    await service.remove_workos_membership(
        workos_user_id=user.workos_user_id,
        workos_organization_id=tenant.workos_organization_id,
    )
    await db_session.commit()

    remaining_membership = await db_session.scalar(
        select(OrgMembership).where(
            OrgMembership.organization_id == tenant.id,
            OrgMembership.user_id == user.id,
        )
    )
    assert remaining_membership is None
    remaining_assignments = (
        await db_session.execute(
            select(RoleAssignment).where(
                RoleAssignment.organization_id == tenant.id,
                RoleAssignment.user_id == user.id,
            )
        )
    ).scalars().all()
    assert remaining_assignments == []


@pytest.mark.asyncio
async def test_remove_workos_membership_is_idempotent_when_local_records_missing(db_session, monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    tenant = Organization(
        name=f"Organization {uuid4().hex[:6]}",
        slug=f"tenant-{uuid4().hex[:8]}",
        workos_organization_id=f"wos_org_{uuid4().hex[:8]}",
    )
    user = User(
        email=f"user-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="user",
        workos_user_id=f"wos_user_{uuid4().hex[:8]}",
    )
    db_session.add_all([tenant, user])
    await db_session.commit()

    service = WorkOSAuthService(db_session)
    await service.remove_workos_membership(
        workos_user_id=user.workos_user_id,
        workos_organization_id=tenant.workos_organization_id,
    )


@pytest.mark.asyncio
async def test_workos_membership_deleted_webhook_is_idempotent(client, db_session, monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_verify_webhook_signature(self, *, payload, sig_header):
        return None

    async def fake_remove_workos_membership(self, *, workos_user_id, workos_organization_id):
        calls.append((workos_user_id, workos_organization_id))

    monkeypatch.setattr(WorkOSAuthService, "verify_webhook_signature", fake_verify_webhook_signature)
    monkeypatch.setattr(WorkOSAuthService, "remove_workos_membership", fake_remove_workos_membership)

    payload = {
        "id": f"evt_membership_deleted_{uuid4().hex[:8]}",
        "event": "organization_membership.deleted",
        "data": {
            "organization_id": "org_workos_123",
            "user_id": "user_workos_123",
        },
    }

    first = await client.post(
        "/webhooks/workos",
        content=json.dumps(payload),
        headers={"workos-signature": "t=1,v1=signature", "content-type": "application/json"},
    )
    second = await client.post(
        "/webhooks/workos",
        content=json.dumps(payload),
        headers={"workos-signature": "t=1,v1=signature", "content-type": "application/json"},
    )

    assert first.status_code == 200
    assert first.json() == {"status": "ok"}
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    assert calls == [("user_workos_123", "org_workos_123")]
