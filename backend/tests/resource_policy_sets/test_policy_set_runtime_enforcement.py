from __future__ import annotations

from uuid import uuid4

import pytest

from app.agent.execution.service import AgentExecutorService
from app.agent.executors.tool import ToolNodeExecutor
from app.db.postgres.models.agents import AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.resource_policies import ResourcePolicyPrincipalType, ResourcePolicyResourceType
from app.services.model_resolver import ModelResolver, ModelResolverError
from app.services.resource_policy_service import ResourcePolicyAccessDenied, ResourcePolicyPrincipalRef
from app.services.retrieval_service import RetrievalService


@pytest.mark.asyncio
async def test_default_internal_run_attaches_resource_policy_snapshot(
    db_session,
    tenant_context,
    resource_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="Default Agent")
    policy_set = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="user-policy")
    await resource_factory.allow_rule(
        policy_set_id=policy_set.id,
        resource_type=ResourcePolicyResourceType.AGENT,
        resource_id=agent.id,
    )
    await resource_factory.assignment(
        tenant_id=tenant.id,
        policy_set_id=policy_set.id,
        created_by=user.id,
        principal_type=ResourcePolicyPrincipalType.TENANT_USER,
        user_id=user.id,
    )
    await db_session.commit()

    run_id = await AgentExecutorService(db_session).start_run(
        agent_id=agent.id,
        input_params={"input": "hello", "context": {}},
        user_id=user.id,
        background=False,
    )
    run = await db_session.get(AgentRun, run_id)

    assert run is not None
    assert run.status == RunStatus.queued
    assert run.input_params["context"]["resource_policy_snapshot"]["direct_policy_set_id"] == str(policy_set.id)
    assert run.input_params["context"]["resource_policy_principal"]["principal_type"] == "tenant_user"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("principal_type", "context_builder"),
    [
        (
            ResourcePolicyPrincipalType.TENANT_USER,
            lambda tenant, user, _agent, _app, _acct: {"user_id": user.id, "context": {}},
        ),
        (
            ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT,
            lambda tenant, user, agent, app, acct: {
                "user_id": user.id,
                "context": {
                    "published_app_id": str(app.id),
                    "published_app_account_id": str(acct.id),
                },
            },
        ),
        (
            ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER,
            lambda tenant, user, agent, _app, _acct: {
                "user_id": user.id,
                "context": {
                    "surface": "embedded_agent_runtime",
                    "external_user_id": "external-1",
                },
            },
        ),
    ],
)
async def test_start_run_denies_restricted_agents_for_all_principal_types(
    db_session,
    tenant_context,
    resource_factory,
    principal_type,
    context_builder,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    allowed_agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="Allowed Agent")
    blocked_agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="Blocked Agent")
    app_agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="App Agent")
    published_app = await resource_factory.published_app(tenant_id=tenant.id, agent_id=app_agent.id)
    app_account = await resource_factory.published_app_account(published_app=published_app)
    policy_set = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name=f"{principal_type.value}-policy")
    await resource_factory.allow_rule(
        policy_set_id=policy_set.id,
        resource_type=ResourcePolicyResourceType.AGENT,
        resource_id=allowed_agent.id,
    )

    if principal_type == ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER:
        blocked_agent.default_embed_policy_set_id = policy_set.id
    await resource_factory.assignment(
        tenant_id=tenant.id,
        policy_set_id=policy_set.id,
        created_by=user.id,
        principal_type=principal_type,
        user_id=user.id if principal_type == ResourcePolicyPrincipalType.TENANT_USER else None,
        published_app_account_id=app_account.id if principal_type == ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT else None,
        embedded_agent_id=blocked_agent.id if principal_type == ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER else None,
        external_user_id="external-1" if principal_type == ResourcePolicyPrincipalType.EMBEDDED_EXTERNAL_USER else None,
    )
    if principal_type == ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT:
        published_app.default_policy_set_id = policy_set.id
    await db_session.commit()

    context_data = context_builder(tenant, user, blocked_agent, published_app, app_account)
    with pytest.raises(ResourcePolicyAccessDenied):
        await AgentExecutorService(db_session).start_run(
            agent_id=blocked_agent.id,
            input_params={"input": "blocked", "context": context_data["context"]},
            user_id=context_data["user_id"],
            background=False,
        )


@pytest.mark.asyncio
async def test_top_level_run_ignores_malformed_snapshot_and_re_resolves_from_assignments(
    db_session,
    tenant_context,
    resource_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="Malformed Snapshot Agent")
    policy_set = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="malformed-fallback")
    await resource_factory.allow_rule(
        policy_set_id=policy_set.id,
        resource_type=ResourcePolicyResourceType.AGENT,
        resource_id=agent.id,
    )
    await resource_factory.assignment(
        tenant_id=tenant.id,
        policy_set_id=policy_set.id,
        created_by=user.id,
        principal_type=ResourcePolicyPrincipalType.TENANT_USER,
        user_id=user.id,
    )
    await db_session.commit()

    run_id = await AgentExecutorService(db_session).start_run(
        agent_id=agent.id,
        input_params={"input": "hello", "context": {"resource_policy_snapshot": {"principal": {"tenant_id": "bad"}}}},
        user_id=user.id,
        background=False,
    )
    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    assert run.input_params["context"]["resource_policy_snapshot"]["direct_policy_set_id"] == str(policy_set.id)


@pytest.mark.asyncio
async def test_model_tool_and_knowledge_store_boundaries_enforce_snapshot(
    db_session,
    tenant_context,
    resource_factory,
    make_snapshot,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    model = await resource_factory.model(tenant_id=tenant.id, name="Allowed Model")
    tool = await resource_factory.tool(tenant_id=tenant.id, name="Blocked Tool")
    knowledge_store = await resource_factory.knowledge_store(tenant_id=tenant.id, name="Blocked Store")

    snapshot = make_snapshot(
        principal=ResourcePolicyPrincipalRef(
            principal_type=ResourcePolicyPrincipalType.TENANT_USER,
            tenant_id=tenant.id,
            user_id=user.id,
        ),
        restricted_resource_types={"tool", "knowledge_store", "model"},
        allowed_models={str(model.id)},
    )

    with pytest.raises(ModelResolverError, match="access denied"):
        await ModelResolver(db_session, tenant.id).resolve_for_execution(str(uuid4()), policy_snapshot=snapshot)

    tool_executor = ToolNodeExecutor(db=db_session, tenant_id=tenant.id)
    with pytest.raises(PermissionError, match="access denied"):
        tool_executor._assert_runtime_policy(
            resource_factory.tool_stub(tool_id=str(tool.id), is_active=True),
            {"resource_policy_snapshot": snapshot.to_payload()},
        )

    with pytest.raises(PermissionError, match="inactive"):
        tool_executor._assert_runtime_policy(
            resource_factory.tool_stub(tool_id=str(tool.id), is_active=False),
            {"resource_policy_snapshot": snapshot.to_payload()},
        )

    with pytest.raises(ResourcePolicyAccessDenied):
        await RetrievalService(db_session).query(
            store_id=knowledge_store.id,
            query="private",
            policy_snapshot=snapshot,
        )


@pytest.mark.asyncio
async def test_nested_agent_call_propagates_frozen_policy_snapshot_even_if_assignment_changes(
    db_session,
    tenant_context,
    resource_factory,
    make_snapshot,
    monkeypatch,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    child_agent = await resource_factory.agent(
        tenant_id=tenant.id,
        created_by=user.id,
        name="Child Agent",
        status=AgentStatus.published,
    )
    tool_executor = ToolNodeExecutor(db=db_session, tenant_id=tenant.id)
    captured: dict[str, object] = {}

    async def fake_start_run(self, *, agent_id, input_params, user_id=None, **kwargs):  # noqa: ANN001
        run_id = uuid4()
        captured["agent_id"] = agent_id
        captured["context"] = input_params["context"]
        await resource_factory.run(
            tenant_id=tenant.id,
            agent_id=agent_id,
            user_id=user_id,
            id=run_id,
            status=RunStatus.completed,
        )
        return run_id

    async def fake_run_and_stream(self, *args, **kwargs):  # noqa: ANN001
        if False:
            yield None

    monkeypatch.setattr("app.agent.execution.service.AgentExecutorService.start_run", fake_start_run)
    monkeypatch.setattr("app.agent.execution.service.AgentExecutorService.run_and_stream", fake_run_and_stream)

    frozen_snapshot = make_snapshot(
        principal=ResourcePolicyPrincipalRef(
            principal_type=ResourcePolicyPrincipalType.TENANT_USER,
            tenant_id=tenant.id,
            user_id=user.id,
        ),
        restricted_resource_types={"agent"},
        allowed_agents={str(child_agent.id)},
    )

    replacement_set = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="replacement")
    await resource_factory.assignment(
        tenant_id=tenant.id,
        policy_set_id=replacement_set.id,
        created_by=user.id,
        principal_type=ResourcePolicyPrincipalType.TENANT_USER,
        user_id=user.id,
    )
    await db_session.commit()

    result = await tool_executor._execute_agent_call_tool(
        None,
        input_data={"input": "hello"},
        implementation_config={"target_agent_id": str(child_agent.id)},
        execution_config={},
        node_context={
            "user_id": str(user.id),
            "resource_policy_snapshot": frozen_snapshot.to_payload(),
            "resource_policy_principal": frozen_snapshot.principal.to_payload(),
        },
    )

    assert result["target_agent_id"] == str(child_agent.id)
    assert captured["agent_id"] == child_agent.id
    assert captured["context"]["resource_policy_snapshot"] == frozen_snapshot.to_payload()
