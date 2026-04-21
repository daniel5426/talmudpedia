from uuid import uuid4

import pytest

from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.workspace import Project
from app.services.security_bootstrap_service import SecurityBootstrapService
from app.services.workos_auth_service import LocalSessionBundle, WorkOSAuthService


@pytest.mark.asyncio
async def test_auth_session_effective_scopes_ignore_workos_permissions(client, db_session, monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", "test-cookie-password")

    tenant = Organization(
        name=f"Organization {uuid4().hex[:6]}",
        slug=f"tenant-{uuid4().hex[:8]}",
        workos_organization_id=f"wos_org_{uuid4().hex[:8]}",
    )
    user = User(email=f"owner-{uuid4().hex[:8]}@example.com", hashed_password="x", role="user")
    db_session.add_all([tenant, user])
    await db_session.flush()

    root = OrgUnit(organization_id=tenant.id, name="Root", slug="root", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    project = Project(
        organization_id=tenant.id,
        name="Project One",
        slug=f"project-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()

    db_session.add(
        OrgMembership(
            organization_id=tenant.id,
            user_id=user.id,
            org_unit_id=root.id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
    )
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(organization_id=tenant.id, user_id=user.id, assigned_by=user.id)
    await db_session.commit()

    state = {"permissions": ["legacy.permission.one"]}

    async def fake_authenticate_request(self, request, response):
        return {"organization_id": tenant.workos_organization_id, "permissions": list(state["permissions"])}

    async def fake_sync_local_user(self, auth_response):
        return user

    async def fake_ensure_local_bundle(self, *, auth_response, request=None, actor_user_id=None):
        return LocalSessionBundle(
            user=user,
            organization=tenant,
            project=project,
            workos_auth=auth_response,
        )

    monkeypatch.setattr(WorkOSAuthService, "is_enabled", staticmethod(lambda: True))
    monkeypatch.setattr(WorkOSAuthService, "authenticate_request", fake_authenticate_request)
    monkeypatch.setattr(WorkOSAuthService, "sync_local_user", fake_sync_local_user)
    monkeypatch.setattr(WorkOSAuthService, "ensure_local_bundle", fake_ensure_local_bundle)
    monkeypatch.setattr(WorkOSAuthService, "current_organization_id", lambda self, auth_response: auth_response["organization_id"])
    monkeypatch.setattr(WorkOSAuthService, "set_project_cookie", lambda self, response, request, project_id: None)

    first = await client.get("/auth/session")
    assert first.status_code == 200
    first_scopes = first.json()["effective_scopes"]

    state["permissions"] = ["legacy.permission.two", "legacy.permission.three"]

    second = await client.get("/auth/session")
    assert second.status_code == 200
    second_scopes = second.json()["effective_scopes"]

    assert first_scopes == second_scopes
    assert "organizations.write" in first_scopes
    assert "projects.write" in first_scopes
