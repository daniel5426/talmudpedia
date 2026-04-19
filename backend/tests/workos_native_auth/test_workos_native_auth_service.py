import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi import Response
from starlette.requests import Request

from app.services.workos_auth_service import WorkOSAuthService


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
