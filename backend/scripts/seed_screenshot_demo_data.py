import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from sqlalchemy import delete, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BACKEND_DIR))

from app.core.env_loader import load_backend_env

load_backend_env(backend_dir=BACKEND_DIR, override=False, required=False)
os.environ.setdefault("DB_TARGET", "local")

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface, AgentThreadStatus
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import OrgMembership, OrgRole, Tenant
from app.db.postgres.models.published_app_analytics import (
    PublishedAppAnalyticsEvent,
    PublishedAppAnalyticsEventType,
    PublishedAppAnalyticsSurface,
)
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppAccount,
    PublishedAppSession,
    PublishedAppStatus,
    PublishedAppVisibility,
)


UTC = timezone.utc


@dataclass(frozen=True)
class DemoAppSpec:
    app_name: str
    app_slug: str
    app_description: str
    source_agent_slugs: Sequence[str]
    source_agent_names: Sequence[str]
    agent_slug: str
    agent_name: str
    agent_description: str
    days: Sequence[dict[str, int]]
    accounts: Sequence[str]


DEMO_SPECS: tuple[DemoAppSpec, ...] = (
    DemoAppSpec(
        app_name="Support Hub",
        app_slug="demo-support-hub",
        app_description="Customer-facing support app for triage, account help, and escalation workflows.",
        source_agent_slugs=("test",),
        source_agent_names=("customer service",),
        agent_slug="support-assistant",
        agent_name="Support Assistant",
        agent_description="Customer support agent for triage, policy guidance, and account-resolution flows.",
        days=(
            {"visits": 14, "runs": 10, "tokens": 9800},
            {"visits": 16, "runs": 12, "tokens": 11000},
            {"visits": 18, "runs": 13, "tokens": 12400},
            {"visits": 15, "runs": 11, "tokens": 10300},
            {"visits": 20, "runs": 15, "tokens": 13800},
            {"visits": 23, "runs": 17, "tokens": 15600},
            {"visits": 19, "runs": 14, "tokens": 13100},
            {"visits": 24, "runs": 18, "tokens": 16300},
            {"visits": 27, "runs": 20, "tokens": 18100},
            {"visits": 22, "runs": 16, "tokens": 14900},
            {"visits": 28, "runs": 21, "tokens": 18900},
            {"visits": 26, "runs": 19, "tokens": 17600},
            {"visits": 30, "runs": 22, "tokens": 19800},
            {"visits": 25, "runs": 18, "tokens": 17100},
        ),
        accounts=("Maya Cohen", "Noam Levi", "Amit Ben-David"),
    ),
    DemoAppSpec(
        app_name="Research Desk",
        app_slug="demo-research-desk",
        app_description="General research workspace for source lookup, summaries, and guided exploration.",
        source_agent_slugs=("sefaria",),
        source_agent_names=("sefaria",),
        agent_slug="research-assistant",
        agent_name="Research Assistant",
        agent_description="Study and research assistant for Talmud, commentary navigation, and source synthesis.",
        days=(
            {"visits": 6, "runs": 4, "tokens": 4200},
            {"visits": 8, "runs": 5, "tokens": 5100},
            {"visits": 7, "runs": 5, "tokens": 4800},
            {"visits": 14, "runs": 10, "tokens": 10900},
            {"visits": 9, "runs": 6, "tokens": 6200},
            {"visits": 18, "runs": 12, "tokens": 13400},
            {"visits": 10, "runs": 7, "tokens": 7100},
            {"visits": 16, "runs": 11, "tokens": 12100},
            {"visits": 11, "runs": 8, "tokens": 7800},
            {"visits": 21, "runs": 14, "tokens": 15800},
            {"visits": 13, "runs": 9, "tokens": 8600},
            {"visits": 17, "runs": 12, "tokens": 12900},
            {"visits": 12, "runs": 8, "tokens": 7900},
            {"visits": 20, "runs": 13, "tokens": 14900},
        ),
        accounts=("Yael Shani", "Eitan Mizrahi"),
    ),
    DemoAppSpec(
        app_name="Sales Workspace",
        app_slug="demo-sales-workspace",
        app_description="Sales app for lead qualification, follow-up drafting, and pipeline support.",
        source_agent_slugs=("prico-demo-agent", "new-prico"),
        source_agent_names=("PRICO Demo Agent", "new prico"),
        agent_slug="sales-copilot",
        agent_name="Sales Copilot",
        agent_description="Finance-facing agent for portfolio review, diligence support, and relationship workflows.",
        days=(
            {"visits": 24, "runs": 18, "tokens": 17100},
            {"visits": 22, "runs": 17, "tokens": 16000},
            {"visits": 18, "runs": 14, "tokens": 13400},
            {"visits": 16, "runs": 12, "tokens": 11800},
            {"visits": 13, "runs": 10, "tokens": 9700},
            {"visits": 11, "runs": 8, "tokens": 7900},
            {"visits": 9, "runs": 7, "tokens": 6800},
            {"visits": 12, "runs": 9, "tokens": 8500},
            {"visits": 14, "runs": 11, "tokens": 10100},
            {"visits": 17, "runs": 13, "tokens": 12000},
            {"visits": 15, "runs": 11, "tokens": 10600},
            {"visits": 13, "runs": 10, "tokens": 9400},
            {"visits": 10, "runs": 8, "tokens": 7600},
            {"visits": 8, "runs": 6, "tokens": 5900},
        ),
        accounts=("Roni Adler", "Lior Barak"),
    ),
    DemoAppSpec(
        app_name="Operations Console",
        app_slug="demo-operations-console",
        app_description="Operator console for queue monitoring, issue handling, and workflow oversight.",
        source_agent_slugs=("platform-architect",),
        source_agent_names=("Platform Architect",),
        agent_slug="operations-planner",
        agent_name="Operations Planner",
        agent_description="Architecture agent for platform planning, operator guidance, and deployment review.",
        days=(
            {"visits": 5, "runs": 4, "tokens": 4600},
            {"visits": 6, "runs": 5, "tokens": 5200},
            {"visits": 8, "runs": 6, "tokens": 6700},
            {"visits": 11, "runs": 8, "tokens": 9100},
            {"visits": 14, "runs": 10, "tokens": 11800},
            {"visits": 18, "runs": 13, "tokens": 14900},
            {"visits": 22, "runs": 16, "tokens": 18400},
            {"visits": 19, "runs": 14, "tokens": 16000},
            {"visits": 15, "runs": 11, "tokens": 12800},
            {"visits": 12, "runs": 9, "tokens": 10300},
            {"visits": 10, "runs": 8, "tokens": 8900},
            {"visits": 9, "runs": 7, "tokens": 7600},
            {"visits": 11, "runs": 8, "tokens": 9400},
            {"visits": 13, "runs": 10, "tokens": 11100},
        ),
        accounts=("Dana Rubin",),
    ),
    DemoAppSpec(
        app_name="Voice Notes",
        app_slug="demo-voice-notes",
        app_description="Transcription and audio-note workspace for recordings, summaries, and action items.",
        source_agent_slugs=("audiosummarizer",),
        source_agent_names=("audio_summarizer",),
        agent_slug="voice-summarizer",
        agent_name="Voice Summarizer",
        agent_description="Audio assistant for transcription cleanup, summaries, and follow-up extraction.",
        days=(
            {"visits": 4, "runs": 3, "tokens": 3600},
            {"visits": 5, "runs": 4, "tokens": 4200},
            {"visits": 4, "runs": 3, "tokens": 3700},
            {"visits": 5, "runs": 4, "tokens": 4500},
            {"visits": 6, "runs": 5, "tokens": 5400},
            {"visits": 8, "runs": 6, "tokens": 6900},
            {"visits": 7, "runs": 5, "tokens": 6200},
            {"visits": 9, "runs": 7, "tokens": 7800},
            {"visits": 7, "runs": 5, "tokens": 6100},
            {"visits": 10, "runs": 8, "tokens": 8600},
            {"visits": 8, "runs": 6, "tokens": 7000},
            {"visits": 11, "runs": 8, "tokens": 9100},
            {"visits": 9, "runs": 7, "tokens": 7600},
            {"visits": 12, "runs": 9, "tokens": 9800},
        ),
        accounts=("Leah Mor", "Niv Harel"),
    ),
    DemoAppSpec(
        app_name="Meeting Briefs",
        app_slug="demo-meeting-briefs",
        app_description="Meeting prep and recap app for notes, summaries, and decision capture.",
        source_agent_slugs=("audio2",),
        source_agent_names=("audio2",),
        agent_slug="meeting-brief-assistant",
        agent_name="Meeting Brief Assistant",
        agent_description="Meeting assistant for agendas, recaps, summaries, and next-step capture.",
        days=(
            {"visits": 9, "runs": 7, "tokens": 7200},
            {"visits": 7, "runs": 5, "tokens": 5600},
            {"visits": 10, "runs": 8, "tokens": 8400},
            {"visits": 8, "runs": 6, "tokens": 6600},
            {"visits": 11, "runs": 8, "tokens": 9000},
            {"visits": 9, "runs": 7, "tokens": 7600},
            {"visits": 13, "runs": 10, "tokens": 10800},
            {"visits": 10, "runs": 8, "tokens": 8500},
            {"visits": 14, "runs": 10, "tokens": 11300},
            {"visits": 11, "runs": 8, "tokens": 9300},
            {"visits": 15, "runs": 11, "tokens": 12100},
            {"visits": 12, "runs": 9, "tokens": 9800},
            {"visits": 16, "runs": 12, "tokens": 12900},
            {"visits": 13, "runs": 10, "tokens": 10600},
        ),
        accounts=("Omer Gal", "Shira Paz", "Tal Ronen"),
    ),
    DemoAppSpec(
        app_name="Document Review",
        app_slug="demo-document-review",
        app_description="Document analysis app for extracting highlights, risks, and summary notes.",
        source_agent_slugs=("artifact-coding-agent",),
        source_agent_names=("Artifact Coding Agent",),
        agent_slug="document-analyst",
        agent_name="Document Analyst",
        agent_description="Analysis agent for documents, comparisons, summaries, and review workflows.",
        days=(
            {"visits": 8, "runs": 6, "tokens": 6300},
            {"visits": 12, "runs": 9, "tokens": 9600},
            {"visits": 17, "runs": 13, "tokens": 14200},
            {"visits": 15, "runs": 11, "tokens": 12000},
            {"visits": 11, "runs": 8, "tokens": 8500},
            {"visits": 9, "runs": 7, "tokens": 7100},
            {"visits": 13, "runs": 10, "tokens": 10300},
            {"visits": 18, "runs": 14, "tokens": 14900},
            {"visits": 16, "runs": 12, "tokens": 13200},
            {"visits": 10, "runs": 8, "tokens": 8200},
            {"visits": 12, "runs": 9, "tokens": 9600},
            {"visits": 19, "runs": 15, "tokens": 15800},
            {"visits": 14, "runs": 11, "tokens": 11700},
            {"visits": 11, "runs": 8, "tokens": 8400},
        ),
        accounts=("Eden Katz", "Gil Sher"),
    ),
    DemoAppSpec(
        app_name="Content Studio",
        app_slug="demo-content-studio",
        app_description="General content workspace for drafting, rewriting, and messaging variations.",
        source_agent_slugs=("published-app-coding-agent", "testsfda"),
        source_agent_names=("Published App Coding Agent", "test"),
        agent_slug="content-assistant",
        agent_name="Content Assistant",
        agent_description="Content agent for drafting, rewriting, variant generation, and structured messaging.",
        days=(
            {"visits": 11, "runs": 9, "tokens": 10100},
            {"visits": 13, "runs": 10, "tokens": 11400},
            {"visits": 12, "runs": 9, "tokens": 10700},
            {"visits": 14, "runs": 11, "tokens": 12300},
            {"visits": 15, "runs": 12, "tokens": 13200},
            {"visits": 16, "runs": 12, "tokens": 13600},
            {"visits": 14, "runs": 11, "tokens": 12500},
            {"visits": 12, "runs": 9, "tokens": 10800},
            {"visits": 10, "runs": 8, "tokens": 9100},
            {"visits": 9, "runs": 7, "tokens": 8200},
            {"visits": 11, "runs": 8, "tokens": 9500},
            {"visits": 13, "runs": 10, "tokens": 11200},
            {"visits": 15, "runs": 12, "tokens": 13100},
            {"visits": 17, "runs": 13, "tokens": 14500},
        ),
        accounts=("Mia Dor", "Yoni Saar", "Ruth Naveh", "Dan Amit"),
    ),
)


def utc_now() -> datetime:
    return datetime.now(UTC)


async def resolve_tenant(session, tenant_slug: str | None, tenant_id: str | None) -> Tenant:
    if tenant_id:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"Tenant not found for id={tenant_id}")
        return tenant

    if tenant_slug:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"Tenant not found for slug={tenant_slug}")
        return tenant

    preferred = (
        await session.execute(
            select(Tenant)
            .where(Tenant.name.ilike("%organization%"))
            .order_by(Tenant.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if preferred is not None:
        return preferred

    tenant = (await session.execute(select(Tenant).order_by(Tenant.created_at.asc()).limit(1))).scalar_one_or_none()
    if tenant is None:
        raise ValueError("No tenant found")
    return tenant


async def resolve_owner_user_id(session, tenant_id) -> str | None:
    membership = (
        await session.execute(
            select(OrgMembership.user_id)
            .where(
                OrgMembership.tenant_id == tenant_id,
                OrgMembership.role == OrgRole.owner,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return membership


async def pick_published_agents(session, tenant_id) -> list[Agent]:
    rows = (
        await session.execute(
            select(Agent)
            .where(
                Agent.tenant_id == tenant_id,
                Agent.status == AgentStatus.published,
            )
            .order_by(Agent.updated_at.desc())
        )
    ).scalars().all()

    by_name = {agent.name: agent for agent in rows}
    by_slug = {agent.slug: agent for agent in rows}
    selected: list[Agent] = []
    seen_ids: set[str] = set()
    for spec in DEMO_SPECS:
        matched = None
        for slug in spec.source_agent_slugs:
            agent = by_slug.get(slug)
            if agent is not None and str(agent.id) not in seen_ids:
                matched = agent
                break
        for name in spec.source_agent_names:
            agent = by_name.get(name)
            if agent is not None and str(agent.id) not in seen_ids:
                matched = agent
                break
        if matched is None:
            for agent in rows:
                if str(agent.id) in seen_ids:
                    continue
                matched = agent
                break
        if matched is not None:
            selected.append(matched)
            seen_ids.add(str(matched.id))
    for agent in rows:
        if str(agent.id) in seen_ids:
            continue
        selected.append(agent)
        seen_ids.add(str(agent.id))
        if len(selected) >= len(DEMO_SPECS):
            break
    if len(selected) < len(DEMO_SPECS):
        raise ValueError(
            f"Need at least {len(DEMO_SPECS)} published agents in tenant {tenant_id}, found {len(selected)}"
        )
    return selected[: len(DEMO_SPECS)]


async def clear_existing_demo_children(session, app_ids: list[str]) -> None:
    if not app_ids:
        return
    await session.execute(
        delete(PublishedAppAnalyticsEvent).where(PublishedAppAnalyticsEvent.published_app_id.in_(app_ids))
    )
    await session.execute(
        delete(AgentRun).where(AgentRun.published_app_id.in_(app_ids))
    )
    await session.execute(
        delete(AgentThread).where(AgentThread.published_app_id.in_(app_ids))
    )
    await session.execute(
        delete(PublishedAppSession).where(PublishedAppSession.published_app_id.in_(app_ids))
    )
    await session.execute(
        delete(PublishedAppAccount).where(PublishedAppAccount.published_app_id.in_(app_ids))
    )


async def delete_obsolete_demo_apps(session, tenant_id) -> None:
    keep_slugs = {spec.app_slug for spec in DEMO_SPECS}
    obsolete_apps = (
        await session.execute(
            select(PublishedApp)
            .where(
                PublishedApp.tenant_id == tenant_id,
                PublishedApp.slug.like("demo-%"),
                PublishedApp.slug.not_in(keep_slugs),
            )
        )
    ).scalars().all()
    if not obsolete_apps:
        return

    obsolete_ids = [app.id for app in obsolete_apps]
    await clear_existing_demo_children(session, obsolete_ids)
    await session.execute(delete(PublishedApp).where(PublishedApp.id.in_(obsolete_ids)))


async def upsert_demo_apps(session, tenant_id, owner_user_id, agents: Sequence[Agent]) -> list[PublishedApp]:
    existing = {
        app.slug: app
        for app in (
            await session.execute(
                select(PublishedApp).where(
                    PublishedApp.tenant_id == tenant_id,
                    PublishedApp.slug.in_([spec.app_slug for spec in DEMO_SPECS]),
                )
            )
        ).scalars().all()
    }

    apps: list[PublishedApp] = []
    now = utc_now()
    for index, (spec, agent) in enumerate(zip(DEMO_SPECS, agents)):
        app = existing.get(spec.app_slug)
        if app is None:
            app = PublishedApp(
                tenant_id=tenant_id,
                agent_id=agent.id,
                name=spec.app_name,
                slug=spec.app_slug,
                description=spec.app_description,
                status=PublishedAppStatus.published,
                visibility=PublishedAppVisibility.public,
                auth_enabled=True,
                auth_providers=["password"],
                auth_template_key="auth-classic",
                template_key="classic-chat",
                created_by=owner_user_id,
                published_at=now - timedelta(minutes=index),
                published_url=f"http://localhost:3000/public/apps/{spec.app_slug}",
            )
            session.add(app)
            await session.flush()
        app.agent_id = agent.id
        app.name = spec.app_name
        app.description = spec.app_description
        app.status = PublishedAppStatus.published
        app.visibility = PublishedAppVisibility.public
        app.auth_enabled = True
        app.auth_providers = ["password"]
        app.auth_template_key = "auth-classic"
        app.template_key = "classic-chat"
        app.created_by = owner_user_id
        app.published_at = now - timedelta(minutes=index)
        app.published_url = f"http://localhost:3000/public/apps/{spec.app_slug}"
        app.updated_at = now - timedelta(minutes=index)
        apps.append(app)
    return apps


def touch_agent(agent: Agent, spec: DemoAppSpec, *, index: int) -> None:
    now = utc_now()
    agent.name = spec.agent_name
    agent.description = spec.agent_description
    agent.updated_at = now - timedelta(minutes=index)


async def seed_app_activity(session, *, app: PublishedApp, agent: Agent, spec: DemoAppSpec) -> None:
    now = utc_now().replace(hour=15, minute=0, second=0, microsecond=0)
    accounts: list[PublishedAppAccount] = []

    for idx, account_name in enumerate(spec.accounts):
        email_local = account_name.lower().replace(" ", ".")
        account = PublishedAppAccount(
            published_app_id=app.id,
            email=f"{email_local}@demo.local",
            full_name=account_name,
            avatar=f"https://api.dicebear.com/7.x/initials/svg?seed={email_local}",
            hashed_password="demo-not-for-login",
            last_login_at=now - timedelta(hours=idx),
            metadata_={"synthetic_demo": True},
            created_at=now - timedelta(days=14 - idx),
            updated_at=now - timedelta(hours=idx),
        )
        session.add(account)
        accounts.append(account)
    await session.flush()

    for idx, account in enumerate(accounts):
        session.add(
            PublishedAppSession(
                published_app_id=app.id,
                app_account_id=account.id,
                jti=f"demo-session-{app.slug}-{idx}",
                provider="password",
                metadata_={"synthetic_demo": True},
                expires_at=now + timedelta(days=30 - idx),
                created_at=now - timedelta(days=idx + 1),
            )
        )

    for day_offset, day_stats in enumerate(spec.days):
        day = now - timedelta(days=len(spec.days) - 1 - day_offset)
        day_accounts = max(1, len(accounts))

        for visit_idx in range(day_stats["visits"]):
            account = accounts[visit_idx % day_accounts] if visit_idx % 3 != 0 else None
            visit_time = day + timedelta(minutes=visit_idx * 7)
            visitor_key = f"demo-visitor-{app.slug}-{day_offset}-{visit_idx}"
            visit_key = f"demo-visit-{app.slug}-{day_offset}-{visit_idx}"
            common = dict(
                tenant_id=app.tenant_id,
                published_app_id=app.id,
                app_account_id=account.id if account else None,
                session_id=None,
                surface=PublishedAppAnalyticsSurface.host_runtime,
                visitor_key=visitor_key,
                visit_key=visit_key,
                path=f"/{app.slug}",
                referer=None,
                user_agent="synthetic-demo-seeder/1.0",
                ip_hash=None,
                metadata_={
                    "synthetic_demo": True,
                    "auth_state": "authenticated" if account else "anonymous",
                },
                occurred_at=visit_time,
            )
            session.add(PublishedAppAnalyticsEvent(event_type=PublishedAppAnalyticsEventType.bootstrap_view, **common))
            session.add(PublishedAppAnalyticsEvent(event_type=PublishedAppAnalyticsEventType.visit_started, **common))

        base_tokens = max(300, int(day_stats["tokens"] / max(1, day_stats["runs"])))
        for run_idx in range(day_stats["runs"]):
            account = accounts[run_idx % day_accounts]
            thread_time = day + timedelta(minutes=90 + run_idx * 13)
            thread = AgentThread(
                tenant_id=app.tenant_id,
                app_account_id=account.id,
                agent_id=agent.id,
                published_app_id=app.id,
                surface=AgentThreadSurface.published_host_runtime,
                title=f"{spec.app_name} thread {day_offset + 1}-{run_idx + 1}",
                status=AgentThreadStatus.active,
                last_activity_at=thread_time + timedelta(minutes=3),
                created_at=thread_time,
                updated_at=thread_time + timedelta(minutes=3),
            )
            session.add(thread)
            await session.flush()

            is_failed = run_idx == 0 and day_offset % 4 == 0
            status = RunStatus.failed if is_failed else RunStatus.completed
            total_tokens = base_tokens + (run_idx * 37)
            run = AgentRun(
                tenant_id=app.tenant_id,
                agent_id=agent.id,
                status=status,
                input_params={"context": {"synthetic_demo": True}},
                output_result={"ok": not is_failed, "synthetic_demo": True},
                error_message="Synthetic timeout" if is_failed else None,
                usage_tokens=total_tokens,
                surface="published_host_runtime",
                published_app_id=app.id,
                published_app_account_id=account.id,
                thread_id=thread.id,
                input_tokens=int(total_tokens * 0.55),
                output_tokens=total_tokens - int(total_tokens * 0.55),
                total_tokens=total_tokens,
                reasoning_tokens=int(total_tokens * 0.12),
                cost_usd=round(total_tokens / 1_000_000, 6),
                started_at=thread_time + timedelta(seconds=15),
                completed_at=thread_time + timedelta(minutes=2, seconds=30),
                created_at=thread_time,
            )
            session.add(run)
            await session.flush()
            thread.last_run_id = run.id


async def run(tenant_slug: str | None, tenant_id: str | None) -> None:
    async with sessionmaker() as session:
        tenant = await resolve_tenant(session, tenant_slug=tenant_slug, tenant_id=tenant_id)
        owner_user_id = await resolve_owner_user_id(session, tenant.id)
        agents = await pick_published_agents(session, tenant.id)
        await delete_obsolete_demo_apps(session, tenant.id)

        for index, (agent, spec) in enumerate(zip(agents, DEMO_SPECS)):
            touch_agent(agent, spec, index=index)

        apps = await upsert_demo_apps(session, tenant.id, owner_user_id, agents)
        await session.flush()
        await clear_existing_demo_children(session, [app.id for app in apps])

        for app, agent, spec in zip(apps, agents, DEMO_SPECS):
            await seed_app_activity(session, app=app, agent=agent, spec=spec)

        await session.commit()

        print(f"Seeded screenshot demo data for tenant {tenant.name} ({tenant.slug})")
        for app, agent in zip(apps, agents):
            print(f"- app={app.name} slug={app.slug} agent={agent.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic demo data for agent/apps screenshots.")
    parser.add_argument("--tenant-slug", help="Target tenant slug")
    parser.add_argument("--tenant-id", help="Target tenant id")
    args = parser.parse_args()
    asyncio.run(run(tenant_slug=args.tenant_slug, tenant_id=args.tenant_id))


if __name__ == "__main__":
    main()
