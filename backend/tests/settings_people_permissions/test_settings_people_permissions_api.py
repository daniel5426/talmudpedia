from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.services.security_bootstrap_service import SecurityBootstrapService
from tests.published_apps._helpers import admin_headers


def _install_fake_workos(monkeypatch):
    class FakeUserManagement:
        def __init__(self):
            self.revoked: list[str] = []

        def list_invitations(self, organization_id):
            return [SimpleNamespace(id="inv-1", email="invitee@example.com", created_at=None, expires_at=None, accepted_at=None)]

        def send_invitation(self, email, organization_id, inviter_user_id=None):
            return SimpleNamespace(id="inv-2", email=email, created_at=None, expires_at=None, accepted_at=None)

        def revoke_invitation(self, invite_id):
            self.revoked.append(invite_id)

    fake_client = SimpleNamespace(user_management=FakeUserManagement())
    monkeypatch.setattr("app.services.workos_auth_service._workos_client", lambda: fake_client)
    return fake_client


@pytest.mark.asyncio
async def test_settings_people_permissions_members_invites_groups_roles_and_assignments(client, db_session, monkeypatch):
    fake_client = _install_fake_workos(monkeypatch)

    tenant = Tenant(
        name=f"Tenant {uuid4().hex[:6]}",
        slug=f"tenant-{uuid4().hex[:8]}",
        workos_organization_id=f"wos_org_{uuid4().hex[:8]}",
    )
    owner = User(email=f"owner-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    member = User(email=f"member-{uuid4().hex[:8]}@example.com", hashed_password="x", role="user", full_name="Member User")
    db_session.add_all([tenant, owner, member])
    await db_session.flush()

    root = OrgUnit(tenant_id=tenant.id, name="Root", slug="root", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()

    db_session.add_all([
        OrgMembership(tenant_id=tenant.id, user_id=owner.id, org_unit_id=root.id, role=OrgRole.owner, status=MembershipStatus.active),
        OrgMembership(tenant_id=tenant.id, user_id=member.id, org_unit_id=root.id, role=OrgRole.member, status=MembershipStatus.active),
    ])
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_owner_assignment(tenant_id=tenant.id, user_id=owner.id, assigned_by=owner.id)
    await db_session.commit()

    headers = admin_headers(str(owner.id), str(tenant.id), str(root.id))

    members_resp = await client.get("/api/settings/people/members", headers=headers)
    assert members_resp.status_code == 200
    assert len(members_resp.json()) == 2

    invites_resp = await client.get("/api/settings/people/invitations", headers=headers)
    assert invites_resp.status_code == 200
    assert invites_resp.json()[0]["id"] == "inv-1"

    invite_create = await client.post(
        "/api/settings/people/invitations",
        headers=headers,
        json={"email": "new@example.com", "project_ids": []},
    )
    assert invite_create.status_code == 201
    assert invite_create.json()["id"] == "inv-2"
    assert invite_create.json()["organization_role"] == "Reader"

    invite_delete = await client.delete("/api/settings/people/invitations/inv-1", headers=headers)
    assert invite_delete.status_code == 204
    assert fake_client.user_management.revoked == ["inv-1"]

    group_create = await client.post(
        "/api/settings/people/groups",
        headers=headers,
        json={"name": "Ops", "slug": "ops", "type": "team", "parent_id": str(root.id)},
    )
    assert group_create.status_code == 201

    role_create = await client.post(
        "/api/settings/people/roles",
        headers=headers,
        json={"family": "organization", "name": "Ops Admin", "description": "Ops role", "permissions": ["projects.read"]},
    )
    assert role_create.status_code == 201
    role_id = role_create.json()["id"]

    project_role_create = await client.post(
        "/api/settings/people/roles",
        headers=headers,
        json={"family": "project", "name": "Ops Admin", "description": "Project ops role", "permissions": ["apps.read", "agents.read"]},
    )
    assert project_role_create.status_code == 201
    project_role_id = project_role_create.json()["id"]

    duplicate_role = await client.post(
        "/api/settings/people/roles",
        headers=headers,
        json={"family": "organization", "name": "Ops Admin", "description": None, "permissions": ["projects.read"]},
    )
    assert duplicate_role.status_code == 400

    invalid_role = await client.post(
        "/api/settings/people/roles",
        headers=headers,
        json={"family": "organization", "name": "Broken Org Role", "description": None, "permissions": ["apps.read"]},
    )
    assert invalid_role.status_code == 400

    roles_resp = await client.get("/api/settings/people/roles", headers=headers)
    assert roles_resp.status_code == 200
    owner_role = next(role for role in roles_resp.json() if role["family"] == "organization" and role["name"] == "Owner")

    preset_update = await client.patch(
        f"/api/settings/people/roles/{owner_role['id']}",
        headers=headers,
        json={"name": "Changed Owner"},
    )
    assert preset_update.status_code == 400
    assert preset_update.json()["detail"] == "Cannot modify system roles"

    preset_delete = await client.delete(f"/api/settings/people/roles/{owner_role['id']}", headers=headers)
    assert preset_delete.status_code == 400
    assert preset_delete.json()["detail"] == "Cannot delete system roles"

    assignment_create = await client.post(
        "/api/settings/people/role-assignments",
        headers=headers,
        json={
            "user_id": str(member.id),
            "role_id": role_id,
            "scope_id": str(tenant.id),
            "scope_type": "organization",
        },
    )
    assert assignment_create.status_code == 201

    invalid_assignment = await client.post(
        "/api/settings/people/role-assignments",
        headers=headers,
        json={
            "user_id": str(member.id),
            "role_id": project_role_id,
            "scope_id": str(tenant.id),
            "scope_type": "organization",
        },
    )
    assert invalid_assignment.status_code == 400
    assert invalid_assignment.json()["detail"] == "Role family does not match assignment scope"

    replacement_role = await client.post(
        "/api/settings/people/roles",
        headers=headers,
        json={"family": "organization", "name": "Ops Auditor", "description": "Audit role", "permissions": ["audit.read"]},
    )
    assert replacement_role.status_code == 201

    replacement_assignment = await client.post(
        "/api/settings/people/role-assignments",
        headers=headers,
        json={
            "user_id": str(member.id),
            "role_id": replacement_role.json()["id"],
            "scope_id": str(tenant.id),
            "scope_type": "organization",
        },
    )
    assert replacement_assignment.status_code == 201

    assignments_resp = await client.get("/api/settings/people/role-assignments", headers=headers)
    assert assignments_resp.status_code == 200
    member_org_assignments = [
        item
        for item in assignments_resp.json()
        if item["user_id"] == str(member.id) and item["scope_type"] == "organization" and item["role_family"] == "organization"
    ]
    assert len(member_org_assignments) == 1
    assert member_org_assignments[0]["role_name"] == "Ops Auditor"
