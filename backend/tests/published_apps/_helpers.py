from datetime import datetime, timezone
from uuid import uuid4

import jwt
from sqlalchemy import delete

from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.agent.execution.service import AgentExecutorService
from app.core.security import ALGORITHM, SECRET_KEY, create_access_token, get_password_hash
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import (
    MembershipStatus,
    OrgMembership,
    OrgUnit,
    OrgUnitType,
    Organization,
    User,
)
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppStatus, PublishedAppVisibility
from app.db.postgres.models.published_apps import (
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.db.postgres.models.workspace import Project
from app.services.published_app_templates import build_template_files, get_template
from app.services.published_app_versioning import create_app_version
from app.services.security_bootstrap_service import SecurityBootstrapService

_ACTIVE_PROJECT_IDS: dict[tuple[str, str, str], str] = {}


async def seed_admin_tenant_and_agent(db_session):
    tenant = Organization(name=f"Organization {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    user = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="admin",
    )
    db_session.add_all([tenant, user])
    await db_session.flush()

    org_unit = OrgUnit(
        organization_id=tenant.id,
        name="Root",
        slug="root",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    membership = OrgMembership(
        organization_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        status=MembershipStatus.active,
    )
    db_session.add(membership)
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(organization_id=tenant.id, user_id=user.id, assigned_by=user.id)
    project = Project(
        organization_id=tenant.id,
        name="Default Project",
        slug=f"project-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()
    await bootstrap.ensure_project_owner_assignment(
        organization_id=tenant.id,
        project_id=project.id,
        user_id=user.id,
        assigned_by=user.id,
    )

    agent = Agent(
        organization_id=tenant.id,
        project_id=project.id,
        name="Published Agent",
        slug=f"agent-{uuid4().hex[:8]}",
        status=AgentStatus.published,
        graph_definition={"nodes": [], "edges": []},
        created_by=user.id,
    )
    db_session.add(agent)
    await db_session.flush()
    await db_session.commit()
    _ACTIVE_PROJECT_IDS[(str(user.id), str(tenant.id), str(org_unit.id))] = str(project.id)
    return tenant, user, org_unit, agent


def admin_headers(user_id: str, organization_id: str, org_unit_id: str, project_id: str | None = None) -> dict[str, str]:
    payload = jwt.decode(
        create_access_token(
            subject=user_id,
            organization_id=organization_id,
            org_unit_id=org_unit_id,
        ),
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )
    payload["scope"] = ["*"]
    project_id = project_id or _ACTIVE_PROJECT_IDS.get((str(user_id), str(organization_id), str(org_unit_id)))
    if project_id:
        payload["project_id"] = str(project_id)
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": organization_id}


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
    organization_id,
    agent_id,
    created_by,
    *,
    project_id=None,
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
    if project_id is None:
        agent = await db_session.get(Agent, agent_id)
        project_id = getattr(agent, "project_id", None) if agent is not None else None
    await db_session.execute(
        delete(PublishedApp).where(PublishedApp.public_id == slug)
    )
    app = PublishedApp(
        organization_id=organization_id,
        project_id=project_id,
        agent_id=agent_id,
        name=f"App {slug}",
        public_id=slug,
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


def install_stub_agent_worker(
    monkeypatch,
    *,
    content: str,
    final_output: dict | None = None,
):
    async def fake_enqueue_background_run(self, run_id):
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        run.dispatch_count = int(getattr(run, "dispatch_count", 0) or 0) + 1
        run.last_dispatched_at = datetime.now(timezone.utc)
        run.execution_owner_kind = "celery"
        run.execution_owner_id = "stub-worker"
        recorder = ExecutionTraceRecorder(serializer=lambda value: value)
        await recorder.save_event(
            run.id,
            self.db,
            {
                "event": "token",
                "sequence": 1,
                "data": {"content": content},
                "visibility": "client_safe",
            },
        )
        run.status = RunStatus.completed
        run.output_result = {
            "final_output": final_output if final_output is not None else {"text": content}
        }
        run.completed_at = datetime.now(timezone.utc)
        run.execution_owner_id = None
        run.execution_lease_expires_at = None
        run.execution_heartbeat_at = None
        await self.db.commit()

    monkeypatch.setattr(
        AgentExecutorService,
        "_enqueue_background_run",
        fake_enqueue_background_run,
    )


def install_app_create_stub(monkeypatch) -> None:
    _ = monkeypatch
