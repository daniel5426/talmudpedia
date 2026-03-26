from __future__ import annotations

import pytest

from app.db.postgres.models.resource_policies import (
    ResourcePolicyPrincipalType,
    ResourcePolicyQuotaUnit,
    ResourcePolicyQuotaWindow,
    ResourcePolicyResourceType,
    ResourcePolicyRuleType,
)
from app.services.resource_policy_service import ResourcePolicyError, ResourcePolicyPrincipalRef, ResourcePolicyService


@pytest.mark.asyncio
async def test_resolve_execution_snapshot_covers_direct_default_override_and_none(
    db_session,
    tenant_context,
    resource_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    embed_agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="Embed Agent")
    app_agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="App Agent")
    published_app = await resource_factory.published_app(tenant_id=tenant.id, agent_id=app_agent.id)
    app_account = await resource_factory.published_app_account(published_app=published_app)

    default_embed = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="embed-default")
    app_default = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="app-default")
    direct_override = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="override")

    embed_agent.default_embed_policy_set_id = default_embed.id
    published_app.default_policy_set_id = app_default.id

    await resource_factory.allow_rule(
        policy_set_id=default_embed.id,
        resource_type=ResourcePolicyResourceType.TOOL,
        resource_id="tool-embed",
    )
    await resource_factory.allow_rule(
        policy_set_id=app_default.id,
        resource_type=ResourcePolicyResourceType.AGENT,
        resource_id="agent-default",
    )
    await resource_factory.allow_rule(
        policy_set_id=direct_override.id,
        resource_type=ResourcePolicyResourceType.KNOWLEDGE_STORE,
        resource_id="ks-override",
    )
    await resource_factory.assignment(
        tenant_id=tenant.id,
        policy_set_id=direct_override.id,
        created_by=user.id,
        principal_type=ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT,
        published_app_account_id=app_account.id,
    )
    await db_session.commit()

    service = ResourcePolicyService(db_session)
    embed_snapshot = await service.resolve_execution_snapshot(
        tenant_id=tenant.id,
        agent_id=embed_agent.id,
        external_user_id="external-1",
    )
    app_snapshot = await service.resolve_execution_snapshot(
        tenant_id=tenant.id,
        agent_id=app_agent.id,
        published_app_id=published_app.id,
        published_app_account_id=app_account.id,
    )
    no_snapshot = await service.resolve_execution_snapshot(
        tenant_id=tenant.id,
        agent_id=app_agent.id,
    )

    assert embed_snapshot is not None
    assert embed_snapshot.principal is not None
    assert embed_snapshot.principal.principal_type == ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER
    assert embed_snapshot.can_use("tool", "tool-embed")

    assert app_snapshot is not None
    assert app_snapshot.direct_policy_set_id == str(direct_override.id)
    assert app_snapshot.source_policy_set_ids == [str(direct_override.id)]
    assert app_snapshot.can_use("knowledge_store", "ks-override")
    assert app_snapshot.can_use("agent", "agent-default")
    assert app_snapshot.restricted_resource_types == {"knowledge_store"}

    assert no_snapshot is None


@pytest.mark.asyncio
async def test_snapshot_build_flattens_includes_round_trips_and_only_restricts_explicit_types(
    db_session,
    tenant_context,
    resource_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    root = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="root")
    nested = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="nested")
    deep = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="deep")
    model_a = await resource_factory.model(tenant_id=tenant.id, name="Model A")
    model_b = await resource_factory.model(tenant_id=tenant.id, name="Model B")

    await resource_factory.include(parent_policy_set_id=root.id, included_policy_set_id=nested.id)
    await resource_factory.include(parent_policy_set_id=nested.id, included_policy_set_id=deep.id)
    await resource_factory.allow_rule(policy_set_id=root.id, resource_type=ResourcePolicyResourceType.AGENT, resource_id="agent-1")
    await resource_factory.allow_rule(policy_set_id=nested.id, resource_type=ResourcePolicyResourceType.TOOL, resource_id="tool-1")
    await resource_factory.quota_rule(policy_set_id=deep.id, model_id=model_a.id, quota_limit=500)
    await resource_factory.quota_rule(policy_set_id=nested.id, model_id=model_b.id, quota_limit=900)
    await db_session.commit()

    service = ResourcePolicyService(db_session)
    principal = ResourcePolicyPrincipalRef(
        principal_type=ResourcePolicyPrincipalType.TENANT_USER,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    snapshot = await service._build_snapshot(principal=principal, direct_policy_set_id=root.id)
    payload = snapshot.to_payload()
    round_trip = type(snapshot).from_payload(payload)

    assert snapshot.source_policy_set_ids == [str(root.id), str(nested.id), str(deep.id)]
    assert snapshot.restricted_resource_types == {"agent", "tool"}
    assert snapshot.can_use("agent", "agent-1")
    assert snapshot.can_use("tool", "tool-1")
    assert snapshot.can_use("knowledge_store", "any-store")
    assert snapshot.get_model_quota(model_a.id).limit_tokens == 500
    assert snapshot.get_model_quota(model_b.id).limit_tokens == 900
    assert round_trip is not None
    assert round_trip.to_payload() == payload


@pytest.mark.asyncio
async def test_validate_policy_set_graph_rejects_cycles_self_include_and_cross_tenant(
    db_session,
    tenant_context,
    secondary_tenant_context,
    resource_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    other_tenant = secondary_tenant_context["tenant"]
    other_user = secondary_tenant_context["user"]
    a = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="a")
    b = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="b")
    foreign = await resource_factory.policy_set(tenant_id=other_tenant.id, created_by=other_user.id, name="foreign")

    await resource_factory.include(parent_policy_set_id=a.id, included_policy_set_id=b.id)
    await resource_factory.include(parent_policy_set_id=b.id, included_policy_set_id=a.id)
    await db_session.flush()

    service = ResourcePolicyService(db_session)
    with pytest.raises(ResourcePolicyError, match="cycle"):
        await service.validate_policy_set_graph(tenant_id=tenant.id, policy_set_id=a.id)

    await db_session.rollback()
    a = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="a2")
    await resource_factory.include(parent_policy_set_id=a.id, included_policy_set_id=a.id)
    await db_session.flush()
    with pytest.raises(ResourcePolicyError, match="cannot include itself"):
        await service.validate_policy_set_graph(tenant_id=tenant.id, policy_set_id=a.id)

    await db_session.rollback()
    local = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="local")
    await resource_factory.include(parent_policy_set_id=local.id, included_policy_set_id=foreign.id)
    await db_session.flush()
    with pytest.raises(ResourcePolicyError, match="not found"):
        await service.validate_policy_set_graph(tenant_id=tenant.id, policy_set_id=local.id)


@pytest.mark.asyncio
async def test_snapshot_build_rejects_conflicting_model_quotas_and_inactive_sets_are_explicit(
    db_session,
    tenant_context,
    resource_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    root = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="root")
    inactive = await resource_factory.policy_set(
        tenant_id=tenant.id,
        created_by=user.id,
        name="inactive",
        is_active=False,
    )
    model = await resource_factory.model(tenant_id=tenant.id, name="Quota Model")
    await resource_factory.include(parent_policy_set_id=root.id, included_policy_set_id=inactive.id)
    await resource_factory.quota_rule(policy_set_id=root.id, model_id=model.id, quota_limit=100)
    await resource_factory.quota_rule(policy_set_id=inactive.id, model_id=model.id, quota_limit=200)
    await db_session.commit()

    service = ResourcePolicyService(db_session)
    principal = ResourcePolicyPrincipalRef(
        principal_type=ResourcePolicyPrincipalType.TENANT_USER,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    with pytest.raises(ResourcePolicyError, match="Conflicting quota rules"):
        await service._build_snapshot(principal=principal, direct_policy_set_id=root.id)

    standalone_inactive = await resource_factory.policy_set(
        tenant_id=tenant.id,
        created_by=user.id,
        name="standalone-inactive",
        is_active=False,
    )
    await resource_factory.allow_rule(
        policy_set_id=standalone_inactive.id,
        resource_type=ResourcePolicyResourceType.TOOL,
        resource_id="inactive-tool",
    )
    await resource_factory.assignment(
        tenant_id=tenant.id,
        policy_set_id=standalone_inactive.id,
        created_by=user.id,
        principal_type=ResourcePolicyPrincipalType.TENANT_USER,
        user_id=user.id,
    )
    await db_session.commit()

    snapshot = await service.resolve_execution_snapshot(
        tenant_id=tenant.id,
        agent_id=(await resource_factory.agent(tenant_id=tenant.id, created_by=user.id)).id,
        user_id=user.id,
    )
    assert snapshot is not None
    assert snapshot.can_use("tool", "inactive-tool")


@pytest.mark.asyncio
async def test_validate_policy_rule_rejects_non_mvp_quota_shapes(db_session):
    service = ResourcePolicyService(db_session)

    await service.validate_policy_rule(
        resource_type=ResourcePolicyResourceType.AGENT,
        rule_type=ResourcePolicyRuleType.ALLOW,
    )

    with pytest.raises(ResourcePolicyError, match="model resources"):
        await service.validate_policy_rule(
            resource_type=ResourcePolicyResourceType.TOOL,
            rule_type=ResourcePolicyRuleType.QUOTA,
            quota_limit=1,
            quota_unit=ResourcePolicyQuotaUnit.TOKENS,
            quota_window=ResourcePolicyQuotaWindow.MONTHLY,
        )

    with pytest.raises(ResourcePolicyError, match="token quotas"):
        await service.validate_policy_rule(
            resource_type=ResourcePolicyResourceType.MODEL,
            rule_type=ResourcePolicyRuleType.QUOTA,
            quota_limit=1,
            quota_unit="requests",  # type: ignore[arg-type]
            quota_window=ResourcePolicyQuotaWindow.MONTHLY,
        )

    with pytest.raises(ResourcePolicyError, match="monthly"):
        await service.validate_policy_rule(
            resource_type=ResourcePolicyResourceType.MODEL,
            rule_type=ResourcePolicyRuleType.QUOTA,
            quota_limit=1,
            quota_unit=ResourcePolicyQuotaUnit.TOKENS,
            quota_window="daily",  # type: ignore[arg-type]
        )

    with pytest.raises(ResourcePolicyError, match="positive integer"):
        await service.validate_policy_rule(
            resource_type=ResourcePolicyResourceType.MODEL,
            rule_type=ResourcePolicyRuleType.QUOTA,
            quota_limit=0,
            quota_unit=ResourcePolicyQuotaUnit.TOKENS,
            quota_window=ResourcePolicyQuotaWindow.MONTHLY,
        )
