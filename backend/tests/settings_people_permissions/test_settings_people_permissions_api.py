from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.postgres.models.identity import MembershipStatus, OrgInvite, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.workspace import Project
from app.services.security_bootstrap_service import SecurityBootstrapService
from tests.published_apps._helpers import admin_headers


def _install_fake_workos(monkeypatch):
    class FakeUserManagement:
        def __init__(self):
            self.revoked: list[str] = []

        def list_invitations(self, organization_id):
            return [SimpleNamespace(id=f"inv-{uuid4().hex[:8]}", email="invitee@example.com", created_at=None, expires_at=None, accepted_at=None)]

        def send_invitation(self, email, organization_id, inviter_user_id=None):
            return SimpleNamespace(id=f"inv-{uuid4().hex[:8]}", email=email, created_at=None, expires_at=None, accepted_at=None)

        def revoke_invitation(self, invite_id):
            self.revoked.append(invite_id)

    fake_client = SimpleNamespace(user_management=FakeUserManagement())
    monkeypatch.setattr("app.services.workos_auth_service._workos_client", lambda: fake_client)
    return fake_client


@pytest.mark.asyncio
async def test_settings_people_permissions_members_invites_groups_roles_and_assignments(client, db_session, monkeypatch):
    fake_client = _install_fake_workos(monkeypatch)

    tenant = Organization(
        name=f"Organization {uuid4().hex[:6]}",
        slug=f"tenant-{uuid4().hex[:8]}",
        workos_organization_id=f"wos_org_{uuid4().hex[:8]}",
    )
    owner = User(email=f"owner-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    member = User(email=f"member-{uuid4().hex[:8]}@example.com", hashed_password="x", role="user", full_name="Member User")
    db_session.add_all([tenant, owner, member])
    await db_session.flush()

    root = OrgUnit(organization_id=tenant.id, name="Root", slug="root", type=OrgUnitType.org)
    db_session.add(root)
    await db_session.flush()
    project = Project(
        organization_id=tenant.id,
        name="Project One",
        slug=f"project-{uuid4().hex[:8]}",
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.flush()

    db_session.add_all([
        OrgMembership(organization_id=tenant.id, user_id=owner.id, org_unit_id=root.id, role=OrgRole.owner, status=MembershipStatus.active),
        OrgMembership(organization_id=tenant.id, user_id=member.id, org_unit_id=root.id, role=OrgRole.member, status=MembershipStatus.active),
    ])
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(organization_id=tenant.id, user_id=owner.id, assigned_by=owner.id)
    await db_session.commit()

    headers = admin_headers(str(owner.id), str(tenant.id), str(root.id))

    members_resp = await client.get("/api/settings/people/members", headers=headers)
    assert members_resp.status_code == 200
    assert len(members_resp.json()) == 2

    invites_resp = await client.get("/api/settings/people/invitations", headers=headers)
    assert invites_resp.status_code == 200
    assert invites_resp.json()[0]["id"].startswith("inv-")

    project_role_create = await client.post(
        "/api/settings/people/roles",
        headers=headers,
        json={"family": "project", "name": "Ops Admin", "description": "Project ops role", "permissions": ["apps.read", "agents.read"]},
    )
    assert project_role_create.status_code == 201
    project_role_id = project_role_create.json()["id"]

    invite_create = await client.post(
        "/api/settings/people/invitations",
        headers=headers,
        json={"email": "new@example.com", "project_ids": [str(project.id)], "project_role_id": project_role_id},
    )
    assert invite_create.status_code == 201
    assert invite_create.json()["id"].startswith("inv-")
    assert invite_create.json()["organization_role"] == "Reader"
    assert invite_create.json()["project_role_id"] == project_role_id
    assert invite_create.json()["project_role"] == "Ops Admin"

    persisted_invite = (
        await db_session.execute(select(OrgInvite).where(OrgInvite.email == "new@example.com", OrgInvite.organization_id == tenant.id))
    ).scalar_one()
    assert persisted_invite.project_ids == [str(project.id)]
    assert str(persisted_invite.project_role_id) == project_role_id

    invite_delete = await client.delete("/api/settings/people/invitations/inv-1", headers=headers)
    assert invite_delete.status_code == 204
    assert fake_client.user_management.revoked == ["inv-1"]

    group_create = await client.post(
        "/api/settings/people/groups",
        headers=headers,
        json={"name": "Ops", "type": "team", "parent_id": str(root.id)},
    )
    assert group_create.status_code == 201

    role_create = await client.post(
        "/api/settings/people/roles",
        headers=headers,
        json={"family": "organization", "name": "Ops Admin", "description": "Ops role", "permissions": ["projects.read"]},
    )
    assert role_create.status_code == 201
    role_id = role_create.json()["id"]

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

    pending_invite_role_delete = await client.delete(f"/api/settings/people/roles/{project_role_id}", headers=headers)
    assert pending_invite_role_delete.status_code == 400
    assert pending_invite_role_delete.json()["detail"] == "Cannot delete role referenced by pending invitations"

    assignment_create = await client.post(
        "/api/settings/people/role-assignments",
        headers=headers,
        json={
            "user_id": str(member.id),
            "role_id": role_id,
            "assignment_kind": "organization",
        },
    )
    assert assignment_create.status_code == 201

    invalid_assignment = await client.post(
        "/api/settings/people/role-assignments",
        headers=headers,
        json={
            "user_id": str(member.id),
            "role_id": project_role_id,
            "assignment_kind": "organization",
        },
    )
    assert invalid_assignment.status_code == 400
    assert invalid_assignment.json()["detail"] == "Role family does not match assignment kind"

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
            "assignment_kind": "organization",
        },
    )
    assert replacement_assignment.status_code == 201

    assignments_resp = await client.get("/api/settings/people/role-assignments", headers=headers)
    assert assignments_resp.status_code == 200
    member_org_assignments = [
        item
        for item in assignments_resp.json()
        if item["user_id"] == str(member.id) and item["assignment_kind"] == "organization" and item["role_family"] == "organization"
    ]
    assert len(member_org_assignments) == 1
    assert member_org_assignments[0]["role_name"] == "Ops Auditor"
