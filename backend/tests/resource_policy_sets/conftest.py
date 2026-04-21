from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.security import get_password_hash
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppAccount
from app.db.postgres.models.rag import KnowledgeStore
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry, ToolRegistry
from app.db.postgres.models.resource_policies import (
    ResourcePolicyAssignment,
    ResourcePolicyPrincipalType,
    ResourcePolicyQuotaUnit,
    ResourcePolicyQuotaWindow,
    ResourcePolicyResourceType,
    ResourcePolicyRule,
    ResourcePolicyRuleType,
    ResourcePolicySet,
    ResourcePolicySetInclude,
)
from app.services.resource_policy_service import ResourcePolicyPrincipalRef, ResourcePolicyQuotaRule, ResourcePolicySnapshot


async def _seed_tenant_with_user(db_session, *, user_role: str = "admin"):
    tenant = Organization(name=f"Organization {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    user = User(
        email=f"user-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role=user_role,
    )
    db_session.add_all([tenant, user])
    await db_session.flush()

    org_unit = OrgUnit(
        organization_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    db_session.add(
        OrgMembership(
            organization_id=tenant.id,
            user_id=user.id,
            org_unit_id=org_unit.id,
            status=MembershipStatus.active,
        )
    )
    await db_session.flush()
    return {"tenant": tenant, "user": user, "org_unit": org_unit}


@pytest_asyncio.fixture
async def tenant_context(db_session):
    return await _seed_tenant_with_user(db_session, user_role="admin")


@pytest_asyncio.fixture
async def secondary_tenant_context(db_session):
    return await _seed_tenant_with_user(db_session, user_role="admin")


@pytest.fixture
def principal_override_factory():
    def _factory(organization_id, user, scopes: list[str], *, principal_type: str = "user"):
        tenant_id_text = str(organization_id)
        user_id_text = str(user.id)
        role_text = str(getattr(user, "role", "admin") or "admin")

        async def _inner():
            if principal_type != "user":
                return {
                    "type": principal_type,
                    "organization_id": tenant_id_text,
                    "user_id": user_id_text,
                    "scopes": scopes,
                }
            return {
                "type": "user",
                "user": user,
                "user_id": user_id_text,
                "organization_id": tenant_id_text,
                "scopes": scopes,
                "role": role_text,
            }

        return _inner

    return _factory


@pytest.fixture
def make_snapshot():
    def _factory(
        *,
        principal: ResourcePolicyPrincipalRef | None = None,
        direct_policy_set_id: str | None = None,
        source_policy_set_ids: list[str] | None = None,
        restricted_resource_types: set[str] | None = None,
        allowed_agents: set[str] | None = None,
        allowed_tools: set[str] | None = None,
        allowed_knowledge_stores: set[str] | None = None,
        allowed_models: set[str] | None = None,
        model_quotas: dict[str, ResourcePolicyQuotaRule] | None = None,
    ) -> ResourcePolicySnapshot:
        return ResourcePolicySnapshot(
            principal=principal,
            direct_policy_set_id=direct_policy_set_id or str(uuid4()),
            source_policy_set_ids=source_policy_set_ids or [str(uuid4())],
            restricted_resource_types=restricted_resource_types or set(),
            allowed_agents=allowed_agents or set(),
            allowed_tools=allowed_tools or set(),
            allowed_knowledge_stores=allowed_knowledge_stores or set(),
            allowed_models=allowed_models or set(),
            model_quotas=model_quotas or {},
        )

    return _factory


@pytest.fixture
def resource_factory(db_session):
    class Factory:
        async def agent(self, *, organization_id, created_by, **overrides):
            agent = Agent(
                organization_id=organization_id,
                name=overrides.pop("name", f"Agent {uuid4().hex[:6]}"),
                slug=overrides.pop("slug", f"agent-{uuid4().hex[:8]}"),
                graph_definition=overrides.pop("graph_definition", {"nodes": [], "edges": []}),
                created_by=created_by,
                **overrides,
            )
            db_session.add(agent)
            await db_session.flush()
            return agent

        async def published_app(self, *, organization_id, agent_id, **overrides):
            published_app = PublishedApp(
                organization_id=organization_id,
                agent_id=agent_id,
                name=overrides.pop("name", f"App {uuid4().hex[:6]}"),
                slug=overrides.pop("slug", f"app-{uuid4().hex[:8]}"),
                **overrides,
            )
            db_session.add(published_app)
            await db_session.flush()
            return published_app

        async def published_app_account(self, *, published_app, **overrides):
            account = PublishedAppAccount(
                published_app=published_app,
                email=overrides.pop("email", f"acct-{uuid4().hex[:8]}@example.com"),
                **overrides,
            )
            db_session.add(account)
            await db_session.flush()
            return account

        async def model(self, *, organization_id, capability_type=ModelCapabilityType.CHAT, **overrides):
            model = ModelRegistry(
                organization_id=organization_id,
                name=overrides.pop("name", f"Model {uuid4().hex[:6]}"),
                capability_type=capability_type,
                **overrides,
            )
            db_session.add(model)
            await db_session.flush()
            return model

        async def tool(self, *, organization_id, **overrides):
            tool = ToolRegistry(
                organization_id=organization_id,
                name=overrides.pop("name", f"Tool {uuid4().hex[:6]}"),
                slug=overrides.pop("slug", f"tool-{uuid4().hex[:8]}"),
                description=overrides.pop("description", "Test tool"),
                schema=overrides.pop("schema", {}),
                is_active=overrides.pop("is_active", True),
                **overrides,
            )
            db_session.add(tool)
            await db_session.flush()
            return tool

        async def knowledge_store(self, *, organization_id, **overrides):
            store = KnowledgeStore(
                organization_id=organization_id,
                name=overrides.pop("name", f"Store {uuid4().hex[:6]}"),
                embedding_model_id=overrides.pop("embedding_model_id", str(uuid4())),
                **overrides,
            )
            db_session.add(store)
            await db_session.flush()
            return store

        async def policy_set(self, *, organization_id, created_by=None, **overrides):
            policy_set = ResourcePolicySet(
                organization_id=organization_id,
                name=overrides.pop("name", f"set-{uuid4().hex[:6]}"),
                created_by=created_by,
                **overrides,
            )
            db_session.add(policy_set)
            await db_session.flush()
            return policy_set

        async def include(self, *, parent_policy_set_id, included_policy_set_id):
            include = ResourcePolicySetInclude(
                parent_policy_set_id=parent_policy_set_id,
                included_policy_set_id=included_policy_set_id,
            )
            db_session.add(include)
            await db_session.flush()
            return include

        async def allow_rule(self, *, policy_set_id, resource_type, resource_id):
            rule = ResourcePolicyRule(
                policy_set_id=policy_set_id,
                resource_type=resource_type,
                resource_id=str(resource_id),
                rule_type=ResourcePolicyRuleType.ALLOW,
            )
            db_session.add(rule)
            await db_session.flush()
            return rule

        async def quota_rule(self, *, policy_set_id, model_id, quota_limit):
            rule = ResourcePolicyRule(
                policy_set_id=policy_set_id,
                resource_type=ResourcePolicyResourceType.MODEL,
                resource_id=str(model_id),
                rule_type=ResourcePolicyRuleType.QUOTA,
                quota_unit=ResourcePolicyQuotaUnit.TOKENS,
                quota_window=ResourcePolicyQuotaWindow.MONTHLY,
                quota_limit=quota_limit,
            )
            db_session.add(rule)
            await db_session.flush()
            return rule

        async def assignment(self, *, organization_id, policy_set_id, created_by, principal_type, **kwargs):
            assignment = ResourcePolicyAssignment(
                organization_id=organization_id,
                policy_set_id=policy_set_id,
                created_by=created_by,
                principal_type=principal_type,
                **kwargs,
            )
            db_session.add(assignment)
            await db_session.flush()
            return assignment

        async def run(self, *, organization_id, agent_id, user_id=None, **overrides):
            run = AgentRun(
                organization_id=organization_id,
                agent_id=agent_id,
                user_id=user_id,
                status=overrides.pop("status", RunStatus.completed),
                input_params=overrides.pop("input_params", {}),
                **overrides,
            )
            db_session.add(run)
            await db_session.flush()
            return run

        def tool_stub(self, *, tool_id, is_active=True, status="published"):
            return SimpleNamespace(id=tool_id, is_active=is_active, status=status, implementation_type=None)

    return Factory()
