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
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppStatus, PublishedAppVisibility
from app.services.security_bootstrap_service import SecurityBootstrapService
from app.services.workload_provisioning_service import WorkloadProvisioningService


async def seed_admin_tenant_and_agent(db_session):
    tenant = Tenant(name=f"Tenant {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    user = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="admin",
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
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_owner_assignment(tenant_id=tenant.id, user_id=user.id, assigned_by=user.id)

    agent = Agent(
        tenant_id=tenant.id,
        name="Published Agent",
        slug=f"agent-{uuid4().hex[:8]}",
        status=AgentStatus.published,
        graph_definition={"nodes": [], "edges": []},
        created_by=user.id,
    )
    db_session.add(agent)
    await db_session.flush()
    await WorkloadProvisioningService(db_session).provision_agent_policy(
        agent=agent,
        actor_user_id=user.id,
    )
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


async def start_publish_version_and_wait(
    client,
    *,
    app_id: str,
    version_id: str,
    headers: dict[str, str],
    attempts: int = 12,
):
    publish_resp = await client.post(
        f"/admin/apps/{app_id}/versions/{version_id}/publish",
        headers=headers,
        json={},
    )
    assert publish_resp.status_code == 200
    job_payload = publish_resp.json()
    job_id = job_payload["job_id"]

    status_payload = job_payload
    for _ in range(attempts):
        if status_payload["status"] in {"succeeded", "failed"}:
            break
        status_resp = await client.get(
            f"/admin/apps/{app_id}/publish/jobs/{job_id}",
            headers=headers,
        )
        assert status_resp.status_code == 200
        status_payload = status_resp.json()
    return job_payload, status_payload


async def start_publish_and_wait(
    client,
    *,
    app_id: str,
    headers: dict[str, str],
    attempts: int = 12,
):
    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    version_id = state_resp.json()["current_draft_revision"]["id"]
    return await start_publish_version_and_wait(
        client,
        app_id=app_id,
        version_id=version_id,
        headers=headers,
        attempts=attempts,
    )


async def seed_published_app(
    db_session,
    tenant_id,
    agent_id,
    created_by,
    *,
    slug: str,
    auth_enabled: bool = True,
    auth_providers=None,
    visibility: PublishedAppVisibility = PublishedAppVisibility.public,
    description: str | None = None,
    logo_url: str | None = None,
    auth_template_key: str = "auth-classic",
    allowed_origins=None,
    external_auth_oidc=None,
):
    app = PublishedApp(
        tenant_id=tenant_id,
        agent_id=agent_id,
        name=f"App {slug}",
        slug=slug,
        description=description,
        logo_url=logo_url,
        visibility=visibility,
        auth_enabled=auth_enabled,
        auth_providers=auth_providers or ["password"],
        auth_template_key=auth_template_key,
        allowed_origins=list(allowed_origins or []),
        external_auth_oidc=dict(external_auth_oidc) if external_auth_oidc else None,
        status=PublishedAppStatus.published,
        created_by=created_by,
        published_url=f"https://{slug}.apps.localhost",
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app
