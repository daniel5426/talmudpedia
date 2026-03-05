from uuid import uuid4

import pytest

from app.core.security import create_access_token, get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.services.security_bootstrap_service import SecurityBootstrapService


def _auth_headers(user_id: str, tenant_id: str, org_unit_id: str, org_role: str = "owner") -> dict[str, str]:
    token = create_access_token(
        subject=user_id,
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        org_role=org_role,
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": tenant_id,
    }


async def _seed_tenant_users(db_session):
    tenant = Tenant(name=f"Tenant {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    owner = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
    )
    member = User(
        email=f"member-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
    )
    db_session.add_all([tenant, owner, member])
    await db_session.flush()

    org_unit = OrgUnit(
        tenant_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    db_session.add_all(
        [
            OrgMembership(
                tenant_id=tenant.id,
                user_id=owner.id,
                org_unit_id=org_unit.id,
                role=OrgRole.owner,
                status=MembershipStatus.active,
            ),
            OrgMembership(
                tenant_id=tenant.id,
                user_id=member.id,
                org_unit_id=org_unit.id,
                role=OrgRole.member,
                status=MembershipStatus.active,
            ),
        ]
    )
    await db_session.flush()

    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_owner_assignment(tenant_id=tenant.id, user_id=owner.id, assigned_by=owner.id)
    await bootstrap.ensure_member_assignment(tenant_id=tenant.id, user_id=member.id, assigned_by=owner.id)
    await db_session.commit()

    return tenant, owner, member, org_unit


@pytest.mark.asyncio
async def test_models_endpoint_requires_tenant_header(client, db_session):
    tenant, owner, _member, org_unit = await _seed_tenant_users(db_session)
    headers = _auth_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    response = await client.get("/models", headers={"Authorization": headers["Authorization"]})
    assert response.status_code == 400
    assert "X-Tenant-ID" in str(response.json())


@pytest.mark.asyncio
async def test_models_list_allows_scoped_owner(client, db_session):
    tenant, owner, _member, org_unit = await _seed_tenant_users(db_session)
    headers = _auth_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    response = await client.get("/models", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert "models" in payload
    assert "total" in payload


@pytest.mark.asyncio
async def test_knowledge_store_create_denied_for_member_without_write_scope(client, db_session):
    tenant, _owner, member, org_unit = await _seed_tenant_users(db_session)
    headers = _auth_headers(str(member.id), str(tenant.id), str(org_unit.id), org_role="member")

    response = await client.post(
        "/admin/knowledge-stores?tenant_slug=" + tenant.slug,
        headers=headers,
        json={
            "name": "Member Attempt",
            "embedding_model_id": "text-embedding-3-small",
            "backend": "pgvector",
            "retrieval_policy": "semantic_only",
        },
    )
    assert response.status_code == 403
    assert "knowledge_stores.write" in str(response.json())
