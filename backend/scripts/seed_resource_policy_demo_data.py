import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

from sqlalchemy import delete, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BACKEND_DIR))

from app.core.env_loader import load_backend_env

load_backend_env(backend_dir=BACKEND_DIR, override=False, required=False)
os.environ.setdefault("DB_TARGET", "local")

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.identity import OrgMembership, OrgRole, Tenant, User
from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppAccount
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry
from app.db.postgres.models.resource_policies import (
    ResourcePolicyAssignment,
    ResourcePolicyPrincipalType,
    ResourcePolicyQuotaCounter,
    ResourcePolicyQuotaReservation,
    ResourcePolicyQuotaUnit,
    ResourcePolicyQuotaWindow,
    ResourcePolicyResourceType,
    ResourcePolicyRule,
    ResourcePolicyRuleType,
    ResourcePolicySet,
    ResourcePolicySetInclude,
)


UTC = timezone.utc


@dataclass(frozen=True)
class RuleSpec:
    resource_type: ResourcePolicyResourceType
    resource_key: str
    rule_type: ResourcePolicyRuleType
    quota_limit: int | None = None


@dataclass(frozen=True)
class SetSpec:
    name: str
    description: str
    is_active: bool
    rules: Sequence[RuleSpec]
    include_names: Sequence[str] = ()


def utc_now() -> datetime:
    return datetime.now(UTC)


SET_SPECS: tuple[SetSpec, ...] = (
    SetSpec(
        name="Baseline Access",
        description="Minimal shared access for general production chat workloads.",
        is_active=True,
        rules=(
            RuleSpec(ResourcePolicyResourceType.MODEL, "chat_primary", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.AGENT, "support_agent", ResourcePolicyRuleType.ALLOW),
        ),
    ),
    SetSpec(
        name="Support Team",
        description="Customer-support access with a capped monthly token budget.",
        is_active=True,
        include_names=("Baseline Access",),
        rules=(
            RuleSpec(ResourcePolicyResourceType.AGENT, "support_agent", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.MODEL, "chat_primary", ResourcePolicyRuleType.QUOTA, 120_000),
        ),
    ),
    SetSpec(
        name="Research Team",
        description="Research-oriented access with a higher monthly analysis quota.",
        is_active=True,
        include_names=("Baseline Access",),
        rules=(
            RuleSpec(ResourcePolicyResourceType.AGENT, "research_agent", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.MODEL, "chat_secondary", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.MODEL, "chat_primary", ResourcePolicyRuleType.QUOTA, 180_000),
        ),
    ),
    SetSpec(
        name="Sales Guardrails",
        description="Lead-handling and follow-up access with tighter spend control.",
        is_active=True,
        include_names=("Baseline Access",),
        rules=(
            RuleSpec(ResourcePolicyResourceType.AGENT, "sales_agent", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.MODEL, "chat_primary", ResourcePolicyRuleType.QUOTA, 90_000),
        ),
    ),
    SetSpec(
        name="Operations Control",
        description="Operational oversight access for queue monitoring and incident response.",
        is_active=True,
        include_names=("Baseline Access",),
        rules=(
            RuleSpec(ResourcePolicyResourceType.AGENT, "ops_agent", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.MODEL, "chat_primary", ResourcePolicyRuleType.QUOTA, 70_000),
        ),
    ),
    SetSpec(
        name="Audio Workspace",
        description="Audio and meeting workflows with medium-volume monthly usage limits.",
        is_active=True,
        include_names=("Baseline Access",),
        rules=(
            RuleSpec(ResourcePolicyResourceType.AGENT, "voice_agent", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.AGENT, "meeting_agent", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.MODEL, "chat_primary", ResourcePolicyRuleType.QUOTA, 85_000),
        ),
    ),
    SetSpec(
        name="Content Review",
        description="Document and content generation flows with controlled drafting access.",
        is_active=True,
        include_names=("Baseline Access",),
        rules=(
            RuleSpec(ResourcePolicyResourceType.AGENT, "document_agent", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.AGENT, "content_agent", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.MODEL, "chat_primary", ResourcePolicyRuleType.QUOTA, 140_000),
        ),
    ),
    SetSpec(
        name="Legacy Restricted",
        description="Inactive legacy policy set kept for migration and screenshot contrast.",
        is_active=False,
        rules=(
            RuleSpec(ResourcePolicyResourceType.AGENT, "document_agent", ResourcePolicyRuleType.ALLOW),
            RuleSpec(ResourcePolicyResourceType.MODEL, "chat_primary", ResourcePolicyRuleType.QUOTA, 25_000),
        ),
    ),
)


async def resolve_tenant(session, tenant_slug: str | None, tenant_id: str | None) -> Tenant:
    if tenant_id:
        tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"Tenant not found for id={tenant_id}")
        return tenant
    if tenant_slug:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"Tenant not found for slug={tenant_slug}")
        return tenant
    tenant = (
        await session.execute(
            select(Tenant).where(Tenant.name.ilike("%organization%")).order_by(Tenant.created_at.asc()).limit(1)
        )
    ).scalar_one_or_none()
    if tenant is None:
        tenant = (await session.execute(select(Tenant).order_by(Tenant.created_at.asc()).limit(1))).scalar_one_or_none()
    if tenant is None:
        raise ValueError("No tenant found")
    return tenant


async def resolve_owner_user_id(session, tenant_id):
    return (
        await session.execute(
            select(OrgMembership.user_id)
            .where(OrgMembership.tenant_id == tenant_id, OrgMembership.role == OrgRole.owner)
            .limit(1)
        )
    ).scalar_one_or_none()


async def load_users(session, tenant_id) -> list[User]:
    return list(
        (
            await session.execute(
                select(User)
                .join(OrgMembership, OrgMembership.user_id == User.id)
                .where(OrgMembership.tenant_id == tenant_id)
                .order_by(User.created_at.asc())
            )
        ).scalars().all()
    )


async def load_published_agents(session, tenant_id) -> list[Agent]:
    return list(
        (
            await session.execute(
                select(Agent)
                .where(Agent.tenant_id == tenant_id, Agent.status == AgentStatus.published)
                .order_by(Agent.updated_at.desc())
            )
        ).scalars().all()
    )


async def load_published_apps(session, tenant_id) -> list[PublishedApp]:
    return list(
        (
            await session.execute(
                select(PublishedApp)
                .where(PublishedApp.tenant_id == tenant_id)
                .order_by(PublishedApp.updated_at.desc())
            )
        ).scalars().all()
    )


async def load_published_app_accounts(session, tenant_id) -> list[PublishedAppAccount]:
    return list(
        (
            await session.execute(
                select(PublishedAppAccount)
                .join(PublishedApp, PublishedApp.id == PublishedAppAccount.published_app_id)
                .where(PublishedApp.tenant_id == tenant_id)
                .order_by(PublishedApp.updated_at.desc(), PublishedAppAccount.created_at.asc())
            )
        ).scalars().all()
    )


async def load_chat_models(session) -> list[ModelRegistry]:
    return list(
        (
            await session.execute(
                select(ModelRegistry)
                .where(
                    ModelRegistry.capability_type == ModelCapabilityType.CHAT,
                    ModelRegistry.is_active == True,
                )
                .order_by(ModelRegistry.created_at.desc())
            )
        ).scalars().all()
    )


def map_agents_by_slug(agents: Iterable[Agent]) -> dict[str, Agent]:
    return {agent.slug: agent for agent in agents}


def require(mapping: dict[str, object], key: str, label: str):
    value = mapping.get(key)
    if value is None:
        raise ValueError(f"Missing required {label}: {key}")
    return value


async def reset_existing_resource_policy_data(session, tenant_id) -> None:
    await session.execute(
        delete(ResourcePolicyQuotaReservation).where(ResourcePolicyQuotaReservation.tenant_id == tenant_id)
    )
    await session.execute(
        delete(ResourcePolicyQuotaCounter).where(ResourcePolicyQuotaCounter.tenant_id == tenant_id)
    )
    await session.execute(
        delete(ResourcePolicyAssignment).where(ResourcePolicyAssignment.tenant_id == tenant_id)
    )
    existing_set_ids = list(
        (
            await session.execute(
                select(ResourcePolicySet.id).where(ResourcePolicySet.tenant_id == tenant_id)
            )
        ).scalars().all()
    )
    if existing_set_ids:
        await session.execute(
            delete(ResourcePolicyRule).where(ResourcePolicyRule.policy_set_id.in_(existing_set_ids))
        )
        await session.execute(
            delete(ResourcePolicySetInclude).where(
                ResourcePolicySetInclude.parent_policy_set_id.in_(existing_set_ids)
            )
        )
        await session.execute(
            delete(ResourcePolicySetInclude).where(
                ResourcePolicySetInclude.included_policy_set_id.in_(existing_set_ids)
            )
        )
        await session.execute(
            delete(ResourcePolicySet).where(ResourcePolicySet.id.in_(existing_set_ids))
        )


async def clear_defaults(session, tenant_id) -> None:
    for app in await load_published_apps(session, tenant_id):
        app.default_policy_set_id = None
    for agent in await load_published_agents(session, tenant_id):
        agent.default_embed_policy_set_id = None


async def create_policy_sets(session, tenant_id, owner_user_id, resource_ids: dict[str, str]) -> dict[str, ResourcePolicySet]:
    created: dict[str, ResourcePolicySet] = {}
    base_time = utc_now() - timedelta(minutes=len(SET_SPECS) + 2)
    for index, spec in enumerate(SET_SPECS):
        created_at = base_time + timedelta(minutes=index)
        policy_set = ResourcePolicySet(
            tenant_id=tenant_id,
            name=spec.name,
            description=spec.description,
            is_active=spec.is_active,
            created_by=owner_user_id,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(policy_set)
        await session.flush()

        for rule_spec in spec.rules:
            session.add(
                ResourcePolicyRule(
                    policy_set_id=policy_set.id,
                    resource_type=rule_spec.resource_type,
                    resource_id=resource_ids[rule_spec.resource_key],
                    rule_type=rule_spec.rule_type,
                    quota_unit=ResourcePolicyQuotaUnit.TOKENS if rule_spec.rule_type == ResourcePolicyRuleType.QUOTA else None,
                    quota_window=ResourcePolicyQuotaWindow.MONTHLY if rule_spec.rule_type == ResourcePolicyRuleType.QUOTA else None,
                    quota_limit=rule_spec.quota_limit if rule_spec.rule_type == ResourcePolicyRuleType.QUOTA else None,
                    created_at=created_at + timedelta(seconds=10),
                    updated_at=created_at + timedelta(seconds=10),
                )
            )
        created[spec.name] = policy_set

    await session.flush()

    for spec in SET_SPECS:
        parent = created[spec.name]
        for included_name in spec.include_names:
            included = created[included_name]
            session.add(
                ResourcePolicySetInclude(
                    parent_policy_set_id=parent.id,
                    included_policy_set_id=included.id,
                    created_at=base_time + timedelta(minutes=20),
                )
            )
    return created


async def create_assignments(
    session,
    *,
    tenant_id,
    owner_user_id,
    policy_sets: dict[str, ResourcePolicySet],
    users: list[User],
    app_accounts: list[PublishedAppAccount],
    agents_by_slug: dict[str, Agent],
) -> None:
    if len(users) >= 1:
        session.add(
            ResourcePolicyAssignment(
                tenant_id=tenant_id,
                principal_type=ResourcePolicyPrincipalType.TENANT_USER,
                policy_set_id=policy_sets["Support Team"].id,
                user_id=users[0].id,
                created_by=owner_user_id,
            )
        )
    if len(users) >= 2:
        session.add(
            ResourcePolicyAssignment(
                tenant_id=tenant_id,
                principal_type=ResourcePolicyPrincipalType.TENANT_USER,
                policy_set_id=policy_sets["Research Team"].id,
                user_id=users[1].id,
                created_by=owner_user_id,
            )
        )

    for idx, (account, set_name) in enumerate(
        zip(
            app_accounts[:4],
            ("Support Team", "Research Team", "Sales Guardrails", "Operations Control"),
        )
    ):
        session.add(
            ResourcePolicyAssignment(
                tenant_id=tenant_id,
                principal_type=ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT,
                policy_set_id=policy_sets[set_name].id,
                published_app_account_id=account.id,
                created_by=owner_user_id,
                created_at=utc_now() + timedelta(seconds=idx),
                updated_at=utc_now() + timedelta(seconds=idx),
            )
        )

    embedded_specs = (
        ("platform-architect", "client-alpha", "Operations Control"),
        ("prico-demo-agent", "partner-ops", "Sales Guardrails"),
        ("artifact-coding-agent", "review-station-7", "Content Review"),
    )
    for idx, (agent_slug, external_user_id, set_name) in enumerate(embedded_specs):
        agent = require(agents_by_slug, agent_slug, "embedded agent")
        session.add(
            ResourcePolicyAssignment(
                tenant_id=tenant_id,
                principal_type=ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER,
                policy_set_id=policy_sets[set_name].id,
                embedded_agent_id=agent.id,
                external_user_id=external_user_id,
                created_by=owner_user_id,
                created_at=utc_now() + timedelta(seconds=20 + idx),
                updated_at=utc_now() + timedelta(seconds=20 + idx),
            )
        )


async def apply_defaults(
    session,
    *,
    apps: list[PublishedApp],
    agents_by_slug: dict[str, Agent],
    policy_sets: dict[str, ResourcePolicySet],
) -> None:
    app_defaults = {
        "Support Hub": "Support Team",
        "Research Desk": "Research Team",
        "Sales Workspace": "Sales Guardrails",
        "Operations Console": "Operations Control",
        "Voice Notes": "Audio Workspace",
        "Meeting Briefs": "Audio Workspace",
        "Document Review": "Content Review",
        "Content Studio": "Content Review",
    }
    for app in apps:
        if app.name in app_defaults:
            app.default_policy_set_id = policy_sets[app_defaults[app.name]].id

    agent_defaults = {
        "test": "Support Team",
        "sefaria": "Research Team",
        "prico-demo-agent": "Sales Guardrails",
        "platform-architect": "Operations Control",
        "audiosummarizer": "Audio Workspace",
        "audio2": "Audio Workspace",
        "artifact-coding-agent": "Content Review",
        "published-app-coding-agent": "Content Review",
    }
    for slug, set_name in agent_defaults.items():
        agent = agents_by_slug.get(slug)
        if agent is not None:
            agent.default_embed_policy_set_id = policy_sets[set_name].id


async def run(tenant_slug: str | None, tenant_id: str | None) -> None:
    async with sessionmaker() as session:
        tenant = await resolve_tenant(session, tenant_slug=tenant_slug, tenant_id=tenant_id)
        owner_user_id = await resolve_owner_user_id(session, tenant.id)
        users = await load_users(session, tenant.id)
        agents = await load_published_agents(session, tenant.id)
        apps = await load_published_apps(session, tenant.id)
        app_accounts = await load_published_app_accounts(session, tenant.id)
        chat_models = await load_chat_models(session)

        if len(chat_models) < 2:
            raise ValueError("Need at least two active chat models for resource policy demo seed")

        agents_by_slug = map_agents_by_slug(agents)
        resource_ids = {
            "support_agent": str(require(agents_by_slug, "test", "agent").id),
            "research_agent": str(require(agents_by_slug, "sefaria", "agent").id),
            "sales_agent": str(require(agents_by_slug, "prico-demo-agent", "agent").id),
            "ops_agent": str(require(agents_by_slug, "platform-architect", "agent").id),
            "voice_agent": str(require(agents_by_slug, "audiosummarizer", "agent").id),
            "meeting_agent": str(require(agents_by_slug, "audio2", "agent").id),
            "document_agent": str(require(agents_by_slug, "artifact-coding-agent", "agent").id),
            "content_agent": str(require(agents_by_slug, "published-app-coding-agent", "agent").id),
            "chat_primary": str(chat_models[0].id),
            "chat_secondary": str(chat_models[1].id),
        }

        await clear_defaults(session, tenant.id)
        await reset_existing_resource_policy_data(session, tenant.id)
        policy_sets = await create_policy_sets(session, tenant.id, owner_user_id, resource_ids)
        await create_assignments(
            session,
            tenant_id=tenant.id,
            owner_user_id=owner_user_id,
            policy_sets=policy_sets,
            users=users,
            app_accounts=app_accounts,
            agents_by_slug=agents_by_slug,
        )
        await apply_defaults(session, apps=apps, agents_by_slug=agents_by_slug, policy_sets=policy_sets)
        await session.commit()

        print(f"Seeded resource policy demo data for tenant {tenant.name} ({tenant.slug})")
        for spec in SET_SPECS:
            print(f"- set={spec.name} active={spec.is_active} includes={len(spec.include_names)} rules={len(spec.rules)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic resource policy data for screenshots.")
    parser.add_argument("--tenant-slug", help="Target tenant slug")
    parser.add_argument("--tenant-id", help="Target tenant id")
    args = parser.parse_args()
    asyncio.run(run(tenant_slug=args.tenant_slug, tenant_id=args.tenant_id))


if __name__ == "__main__":
    main()
