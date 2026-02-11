from uuid import uuid4

from app.core.security import create_access_token, get_password_hash
from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.identity import (
    MembershipStatus,
    OrgMembership,
    OrgRole,
    OrgUnit,
    OrgUnitType,
    Tenant,
    User,
)
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppStatus


async def seed_admin_tenant_and_agent(db_session):
    tenant = Tenant(name=f"Tenant {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    user = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
    )
    db_session.add_all([tenant, user])
    await db_session.flush()

    org_unit = OrgUnit(
        tenant_id=tenant.id,
        name="Root",
        slug="root",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    membership = OrgMembership(
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add(membership)

    agent = Agent(
        tenant_id=tenant.id,
        name="Published Agent",
        slug=f"agent-{uuid4().hex[:8]}",
        status=AgentStatus.published,
        graph_definition={"nodes": [], "edges": []},
        created_by=user.id,
    )
    db_session.add(agent)
    await db_session.commit()
    return tenant, user, org_unit, agent


def admin_headers(user_id: str, tenant_id: str, org_unit_id: str) -> dict[str, str]:
    token = create_access_token(
        subject=user_id,
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        org_role="owner",
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}


async def seed_published_app(db_session, tenant_id, agent_id, created_by, *, slug: str, auth_enabled: bool = True, auth_providers=None):
    app = PublishedApp(
        tenant_id=tenant_id,
        agent_id=agent_id,
        name=f"App {slug}",
        slug=slug,
        auth_enabled=auth_enabled,
        auth_providers=auth_providers or ["password"],
        status=PublishedAppStatus.published,
        created_by=created_by,
        published_url=f"https://{slug}.apps.localhost",
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app
