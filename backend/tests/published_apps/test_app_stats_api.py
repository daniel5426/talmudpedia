from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface, AgentThreadStatus
from app.db.postgres.models.published_app_analytics import (
    PublishedAppAnalyticsEvent,
    PublishedAppAnalyticsEventType,
    PublishedAppAnalyticsSurface,
)
from app.db.postgres.models.published_apps import (
    PublishedAppAccount,
    PublishedAppAccountStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
    PublishedAppSession,
)
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent, seed_published_app


def _host_headers(slug: str) -> dict[str, str]:
    return {"Host": f"{slug}.apps.localhost"}


async def _attach_published_revision(db_session, app, *, created_by):
    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.published,
        template_key=app.template_key,
        entry_file="src/main.tsx",
        files={},
        manifest_json={},
        build_status=PublishedAppRevisionBuildStatus.succeeded,
        version_seq=1,
        origin_kind="test",
        created_by=created_by,
    )
    db_session.add(revision)
    await db_session.flush()
    app.current_published_revision_id = revision.id
    await db_session.commit()
    await db_session.refresh(app)
    return revision


@pytest.mark.asyncio
async def test_host_bootstrap_tracks_bootstrap_views_and_dedupes_visits(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="stats-host-bootstrap-app",
        auth_enabled=False,
    )
    await _attach_published_revision(db_session, app, created_by=owner.id)

    first = await client.get("/_talmudpedia/runtime/bootstrap", headers=_host_headers(app.public_id))
    assert first.status_code == 200
    second = await client.get("/_talmudpedia/runtime/bootstrap", headers=_host_headers(app.public_id))
    assert second.status_code == 200

    events = list(
        (
            await db_session.execute(
                select(PublishedAppAnalyticsEvent)
                .where(PublishedAppAnalyticsEvent.published_app_id == app.id)
                .order_by(PublishedAppAnalyticsEvent.occurred_at.asc())
            )
        ).scalars().all()
    )
    assert len(events) == 3
    assert [event.event_type for event in events].count(PublishedAppAnalyticsEventType.bootstrap_view) == 2
    assert [event.event_type for event in events].count(PublishedAppAnalyticsEventType.visit_started) == 1

    visit_started = next(event for event in events if event.event_type == PublishedAppAnalyticsEventType.visit_started)
    visit_started.occurred_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    await db_session.commit()

    third = await client.get("/_talmudpedia/runtime/bootstrap", headers=_host_headers(app.public_id))
    assert third.status_code == 200

    visits_after = list(
        (
            await db_session.execute(
                select(PublishedAppAnalyticsEvent).where(
                    PublishedAppAnalyticsEvent.published_app_id == app.id,
                    PublishedAppAnalyticsEvent.event_type == PublishedAppAnalyticsEventType.visit_started,
                )
            )
        ).scalars().all()
    )
    assert len(visits_after) == 2


@pytest.mark.asyncio
async def test_external_bootstrap_associates_authenticated_app_account(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="stats-external-auth-app",
        allowed_origins=["https://client.example.com"],
    )
    await _attach_published_revision(db_session, app, created_by=owner.id)

    signup_resp = await client.post(
        f"/public/external/apps/{app.public_id}/auth/signup",
        headers={"Origin": "https://client.example.com"},
        json={"email": "stats-auth@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    token = signup_resp.json()["token"]

    bootstrap_resp = await client.get(
        f"/public/external/apps/{app.public_id}/runtime/bootstrap",
        headers={
            "Origin": "https://client.example.com",
            "Authorization": f"Bearer {token}",
        },
    )
    assert bootstrap_resp.status_code == 200

    latest_view = (
        await db_session.execute(
            select(PublishedAppAnalyticsEvent)
            .where(
                PublishedAppAnalyticsEvent.published_app_id == app.id,
                PublishedAppAnalyticsEvent.event_type == PublishedAppAnalyticsEventType.bootstrap_view,
            )
            .order_by(PublishedAppAnalyticsEvent.occurred_at.desc())
            .limit(1)
        )
    ).scalar_one()
    assert latest_view.app_account_id is not None
    assert latest_view.surface == PublishedAppAnalyticsSurface.external_runtime


@pytest.mark.asyncio
async def test_admin_apps_stats_returns_app_level_metrics(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="stats-aggregate-app",
        auth_enabled=False,
    )

    account = PublishedAppAccount(
        published_app_id=app.id,
        email="metrics@example.com",
        status=PublishedAppAccountStatus.active,
    )
    db_session.add(account)
    await db_session.flush()
    session = PublishedAppSession(
        published_app_id=app.id,
        app_account_id=account.id,
        jti=str(uuid4()),
        provider="password",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(session)
    thread = AgentThread(
        organization_id=tenant.id,
        app_account_id=account.id,
        agent_id=agent.id,
        published_app_id=app.id,
        surface=AgentThreadSurface.published_host_runtime,
        status=AgentThreadStatus.active,
        title="Metrics thread",
        created_at=datetime.now(timezone.utc),
        last_activity_at=datetime.now(timezone.utc),
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        AgentRun(
            organization_id=tenant.id,
            agent_id=agent.id,
            thread_id=thread.id,
            published_app_id=app.id,
            published_app_account_id=account.id,
            status=RunStatus.completed,
            usage_tokens=42,
            input_params={"context": {}},
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        PublishedAppAnalyticsEvent(
            organization_id=tenant.id,
            published_app_id=app.id,
            app_account_id=account.id,
            session_id=session.id,
            event_type=PublishedAppAnalyticsEventType.bootstrap_view,
            surface=PublishedAppAnalyticsSurface.host_runtime,
            visitor_key=f"app_account:{account.id}",
            visit_key="visit-1",
            metadata_={"auth_state": "authenticated"},
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        PublishedAppAnalyticsEvent(
            organization_id=tenant.id,
            published_app_id=app.id,
            app_account_id=account.id,
            session_id=session.id,
            event_type=PublishedAppAnalyticsEventType.visit_started,
            surface=PublishedAppAnalyticsSurface.host_runtime,
            visitor_key=f"app_account:{account.id}",
            visit_key="visit-1",
            metadata_={"auth_state": "authenticated"},
            occurred_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    response = await client.get("/admin/apps/stats?days=7", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    stats_item = next(item for item in payload["items"] if item["app_id"] == str(app.id))
    assert stats_item["visits"] == 1
    assert stats_item["unique_visitors"] == 1
    assert stats_item["agent_runs"] == 1
    assert stats_item["failed_runs"] == 0
    assert stats_item["tokens"] == 42
    assert stats_item["threads"] == 1
    assert stats_item["app_accounts"] == 1
    assert stats_item["active_sessions"] == 1

    detail_response = await client.get(f"/admin/apps/{app.id}/stats?days=7", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["app_id"] == str(app.id)
