from __future__ import annotations

import pytest

from app.api.dependencies import get_current_principal
from app.db.postgres.models.resource_policies import (
    ResourcePolicyPrincipalType,
    ResourcePolicyResourceType,
    ResourcePolicyRuleType,
)
from main import app


@pytest.mark.asyncio
async def test_policy_set_crud_and_scope_enforcement(
    client,
    db_session,
    tenant_context,
    principal_override_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    app.dependency_overrides[get_current_principal] = principal_override_factory(tenant.id, user, ["roles.read"])
    try:
        forbidden = await client.post(
            "/admin/security/resource-policies/sets",
            json={"name": "Readers Only", "is_active": True},
        )
        assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_current_principal] = principal_override_factory(
        tenant.id,
        user,
        ["roles.read", "roles.write"],
    )
    try:
        create_resp = await client.post(
            "/admin/security/resource-policies/sets",
            json={"name": "Power Users", "description": "main set", "is_active": True},
        )
        assert create_resp.status_code == 201, create_resp.text
        created = create_resp.json()

        duplicate_resp = await client.post(
            "/admin/security/resource-policies/sets",
            json={"name": "Power Users", "is_active": True},
        )
        assert duplicate_resp.status_code == 409

        list_resp = await client.get("/admin/security/resource-policies/sets")
        assert list_resp.status_code == 200
        assert [item["id"] for item in list_resp.json()] == [created["id"]]

        get_resp = await client.get(f"/admin/security/resource-policies/sets/{created['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Power Users"

        update_resp = await client.patch(
            f"/admin/security/resource-policies/sets/{created['id']}",
            json={"name": "Power Users Plus", "is_active": False},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Power Users Plus"
        assert update_resp.json()["is_active"] is False

        delete_resp = await client.delete(f"/admin/security/resource-policies/sets/{created['id']}")
        assert delete_resp.status_code == 204
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_policy_set_names_are_tenant_scoped(
    client,
    tenant_context,
    secondary_tenant_context,
    principal_override_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    other_tenant = secondary_tenant_context["tenant"]
    other_user = secondary_tenant_context["user"]

    app.dependency_overrides[get_current_principal] = principal_override_factory(
        tenant.id,
        user,
        ["roles.read", "roles.write"],
    )
    try:
        first_resp = await client.post(
            "/admin/security/resource-policies/sets",
            json={"name": "Shared Name", "is_active": True},
        )
        assert first_resp.status_code == 201
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_current_principal] = principal_override_factory(
        other_tenant.id,
        other_user,
        ["roles.read", "roles.write"],
    )
    try:
        second_resp = await client.post(
            "/admin/security/resource-policies/sets",
            json={"name": "Shared Name", "is_active": True},
        )
        assert second_resp.status_code == 201
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_include_rule_and_assignment_routes_cover_conflicts_and_cross_tenant_rejections(
    client,
    db_session,
    tenant_context,
    secondary_tenant_context,
    resource_factory,
    principal_override_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    other_tenant = secondary_tenant_context["tenant"]
    other_user = secondary_tenant_context["user"]
    primary = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="primary")
    included = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="included")
    foreign = await resource_factory.policy_set(tenant_id=other_tenant.id, created_by=other_user.id, name="foreign")
    model = await resource_factory.model(tenant_id=tenant.id, name="Quota Model")
    second_model = await resource_factory.model(tenant_id=tenant.id, name="Quota Model 2")
    third_model = await resource_factory.model(tenant_id=tenant.id, name="Quota Model 3")
    published_agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="Published Agent")
    published_app = await resource_factory.published_app(tenant_id=tenant.id, agent_id=published_agent.id)
    app_account = await resource_factory.published_app_account(published_app=published_app)
    embed_agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="Embed Agent")
    foreign_embed_agent = await resource_factory.agent(tenant_id=other_tenant.id, created_by=other_user.id, name="Other Embed")
    await db_session.commit()
    primary_id = str(primary.id)
    included_id = str(included.id)
    foreign_id = str(foreign.id)
    app_account_id = str(app_account.id)
    embed_agent_id = str(embed_agent.id)
    foreign_embed_agent_id = str(foreign_embed_agent.id)
    user_id = str(user.id)
    model_id = str(model.id)
    second_model_id = str(second_model.id)
    third_model_id = str(third_model.id)

    app.dependency_overrides[get_current_principal] = principal_override_factory(
        tenant.id,
        user,
        ["roles.read", "roles.write"],
    )
    try:
        include_resp = await client.post(
            f"/admin/security/resource-policies/sets/{primary_id}/includes",
            json={"included_policy_set_id": included_id},
        )
        assert include_resp.status_code == 200, include_resp.text
        assert include_resp.json()["included_policy_set_ids"] == [included_id]

        duplicate_include = await client.post(
            f"/admin/security/resource-policies/sets/{primary_id}/includes",
            json={"included_policy_set_id": included_id},
        )
        assert duplicate_include.status_code == 409

        cycle_resp = await client.post(
            f"/admin/security/resource-policies/sets/{included_id}/includes",
            json={"included_policy_set_id": primary_id},
        )
        assert cycle_resp.status_code == 400

        foreign_include = await client.post(
            f"/admin/security/resource-policies/sets/{primary_id}/includes",
            json={"included_policy_set_id": foreign_id},
        )
        assert foreign_include.status_code == 404

        allow_resp = await client.post(
            f"/admin/security/resource-policies/sets/{primary_id}/rules",
            json={
                "resource_type": "tool",
                "resource_id": "tool-1",
                "rule_type": "allow",
            },
        )
        assert allow_resp.status_code == 201

        quota_resp = await client.post(
            f"/admin/security/resource-policies/sets/{primary_id}/rules",
            json={
                "resource_type": "model",
                "resource_id": model_id,
                "rule_type": "quota",
                "quota_unit": "tokens",
                "quota_window": "monthly",
                "quota_limit": 1000,
            },
        )
        assert quota_resp.status_code == 201
        second_quota_resp = await client.post(
            f"/admin/security/resource-policies/sets/{primary_id}/rules",
            json={
                "resource_type": "model",
                "resource_id": third_model_id,
                "rule_type": "quota",
                "quota_unit": "tokens",
                "quota_window": "monthly",
                "quota_limit": 2000,
            },
        )
        assert second_quota_resp.status_code == 201

        invalid_quota = await client.post(
            f"/admin/security/resource-policies/sets/{primary_id}/rules",
            json={
                "resource_type": "tool",
                "resource_id": "tool-2",
                "rule_type": "quota",
                "quota_unit": "tokens",
                "quota_window": "monthly",
                "quota_limit": 1000,
            },
        )
        assert invalid_quota.status_code == 400

        update_rule = await client.patch(
            f"/admin/security/resource-policies/rules/{quota_resp.json()['id']}",
            json={"resource_id": second_model_id, "quota_limit": 1500},
        )
        assert update_rule.status_code == 200
        assert update_rule.json()["resource_id"] == second_model_id
        assert update_rule.json()["quota_limit"] == 1500

        conflict_rule = await client.patch(
            f"/admin/security/resource-policies/rules/{update_rule.json()['id']}",
            json={"resource_id": third_model_id},
        )
        assert conflict_rule.status_code == 409

        list_assignments = await client.get("/admin/security/resource-policies/assignments")
        assert list_assignments.status_code == 200
        assert list_assignments.json() == []

        user_assignment = await client.put(
            "/admin/security/resource-policies/assignments",
            json={
                "principal_type": "tenant_user",
                "policy_set_id": primary_id,
                "user_id": user_id,
            },
        )
        assert user_assignment.status_code == 200

        app_assignment = await client.put(
            "/admin/security/resource-policies/assignments",
            json={
                "principal_type": "published_app_account",
                "policy_set_id": primary_id,
                "published_app_account_id": app_account_id,
            },
        )
        assert app_assignment.status_code == 200

        embedded_assignment = await client.put(
            "/admin/security/resource-policies/assignments",
            json={
                "principal_type": "embedded_external_user",
                "policy_set_id": primary_id,
                "embedded_agent_id": embed_agent_id,
                "external_user_id": "external-1",
            },
        )
        assert embedded_assignment.status_code == 200

        upsert_assignment = await client.put(
            "/admin/security/resource-policies/assignments",
            json={
                "principal_type": "tenant_user",
                "policy_set_id": included_id,
                "user_id": user_id,
            },
        )
        assert upsert_assignment.status_code == 200
        assert upsert_assignment.json()["policy_set_id"] == included_id

        cross_tenant_assignment = await client.put(
            "/admin/security/resource-policies/assignments",
            json={
                "principal_type": "embedded_external_user",
                "policy_set_id": primary_id,
                "embedded_agent_id": foreign_embed_agent_id,
                "external_user_id": "external-2",
            },
        )
        assert cross_tenant_assignment.status_code == 404

        delete_assignment = await client.delete(
            "/admin/security/resource-policies/assignments",
            params={
                "principal_type": "published_app_account",
                "published_app_account_id": app_account_id,
            },
        )
        assert delete_assignment.status_code == 204

        missing_assignment = await client.delete(
            "/admin/security/resource-policies/assignments",
            params={
                "principal_type": "published_app_account",
                "published_app_account_id": app_account_id,
            },
        )
        assert missing_assignment.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_default_policy_routes_and_non_user_principals_are_rejected(
    client,
    db_session,
    tenant_context,
    secondary_tenant_context,
    resource_factory,
    principal_override_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    other_tenant = secondary_tenant_context["tenant"]
    other_user = secondary_tenant_context["user"]
    agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="Default Agent")
    published_app = await resource_factory.published_app(tenant_id=tenant.id, agent_id=agent.id)
    default_set = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="default")
    foreign_set = await resource_factory.policy_set(tenant_id=other_tenant.id, created_by=other_user.id, name="foreign")
    await db_session.commit()

    app.dependency_overrides[get_current_principal] = principal_override_factory(
        tenant.id,
        user,
        ["roles.read", "roles.write"],
    )
    try:
        set_app_default = await client.patch(
            f"/admin/security/resource-policies/published-apps/{published_app.id}/default-policy-set",
            json={"policy_set_id": str(default_set.id)},
        )
        assert set_app_default.status_code == 204

        clear_app_default = await client.patch(
            f"/admin/security/resource-policies/published-apps/{published_app.id}/default-policy-set",
            json={"policy_set_id": None},
        )
        assert clear_app_default.status_code == 204

        set_embed_default = await client.patch(
            f"/admin/security/resource-policies/embedded-agents/{agent.id}/default-policy-set",
            json={"policy_set_id": str(default_set.id)},
        )
        assert set_embed_default.status_code == 204

        foreign_default = await client.patch(
            f"/admin/security/resource-policies/embedded-agents/{agent.id}/default-policy-set",
            json={"policy_set_id": str(foreign_set.id)},
        )
        assert foreign_default.status_code == 404
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_current_principal] = principal_override_factory(
        tenant.id,
        user,
        ["roles.read", "roles.write"],
        principal_type="workload",
    )
    try:
        rejected = await client.get("/admin/security/resource-policies/sets")
        assert rejected.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_default_policy_ids_are_exposed_by_apps_and_agents_list_endpoints(
    client,
    db_session,
    tenant_context,
    resource_factory,
    principal_override_factory,
):
    tenant = tenant_context["tenant"]
    user = tenant_context["user"]
    agent = await resource_factory.agent(tenant_id=tenant.id, created_by=user.id, name="Default Agent")
    published_app = await resource_factory.published_app(tenant_id=tenant.id, agent_id=agent.id, name="Default App")
    default_set = await resource_factory.policy_set(tenant_id=tenant.id, created_by=user.id, name="default")
    agent.default_embed_policy_set_id = default_set.id
    published_app.default_policy_set_id = default_set.id
    await db_session.commit()

    app.dependency_overrides[get_current_principal] = principal_override_factory(
        tenant.id,
        user,
        ["roles.read", "apps.read", "agents.read"],
    )
    try:
        list_apps_resp = await client.get("/admin/apps")
        assert list_apps_resp.status_code == 200, list_apps_resp.text
        assert list_apps_resp.json()[0]["default_policy_set_id"] == str(default_set.id)

        list_agents_resp = await client.get("/agents?compact=true")
        assert list_agents_resp.status_code == 200, list_agents_resp.text
        assert list_agents_resp.json()["agents"][0]["default_embed_policy_set_id"] == str(default_set.id)
    finally:
        app.dependency_overrides.clear()
