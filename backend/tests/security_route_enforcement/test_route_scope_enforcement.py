from uuid import uuid4

import pytest
import jwt

from app.core.security import ALGORITHM, SECRET_KEY, create_access_token, get_password_hash
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Organization, User
from app.services.security_bootstrap_service import SecurityBootstrapService


def _auth_headers(
    user_id: str,
    organization_id: str,
    org_unit_id: str,
    org_role: str = "owner",
    scopes: list[str] | None = None,
) -> dict[str, str]:
    payload = jwt.decode(
        create_access_token(
            subject=user_id,
            organization_id=organization_id,
            org_unit_id=org_unit_id,
            org_role=org_role,
        ),
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )
    payload["scope"] = scopes if scopes is not None else (["*"] if org_role == "owner" else [])
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": organization_id,
    }


async def _seed_tenant_users(db_session):
    tenant = Organization(name=f"Organization {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
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
        organization_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    db_session.add_all(
        [
            OrgMembership(
                organization_id=tenant.id,
                user_id=owner.id,
                org_unit_id=org_unit.id,
                role=OrgRole.owner,
                status=MembershipStatus.active,
            ),
            OrgMembership(
                organization_id=tenant.id,
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
    await bootstrap.ensure_organization_owner_assignment(organization_id=tenant.id, user_id=owner.id, assigned_by=owner.id)
    await bootstrap.ensure_organization_reader_assignment(organization_id=tenant.id, user_id=member.id, assigned_by=owner.id)
    await db_session.commit()

    return tenant, owner, member, org_unit


@pytest.mark.asyncio
async def test_models_endpoint_requires_organization_header(client, db_session):
    tenant, owner, _member, org_unit = await _seed_tenant_users(db_session)
    headers = _auth_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    response = await client.get("/models", headers={"Authorization": headers["Authorization"]})
    assert response.status_code == 400
    assert "Active organization context is required" in str(response.json())


@pytest.mark.asyncio
async def test_models_list_allows_scoped_owner(client, db_session):
    tenant, owner, _member, org_unit = await _seed_tenant_users(db_session)
    headers = _auth_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    response = await client.get("/models", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
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
