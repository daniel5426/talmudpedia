from __future__ import annotations

import pytest

from app.services.organization_api_key_service import OrganizationAPIKeyService
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_headers(tenant, owner, org_unit):
    return admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))


async def _create_key(db_session, *, organization_id, created_by, name="Embed Key", scopes=None):
    api_key, token = await OrganizationAPIKeyService(db_session).create_api_key(
        organization_id=organization_id,
        name=name,
        scopes=scopes or ["agents.embed"],
        created_by=created_by,
    )
    await db_session.commit()
    return api_key, token


@pytest.mark.asyncio
async def test_api_keys_create_list_and_revoke(client, db_session):
    tenant, owner, org_unit, _ = await seed_admin_tenant_and_agent(db_session)
    headers = await _create_headers(tenant, owner, org_unit)

    create_resp = await client.post(
        "/admin/organizations/api-keys",
        headers=headers,
        json={"name": "Embed Production", "scopes": ["agents.embed"]},
    )
    assert create_resp.status_code == 201
    payload = create_resp.json()
    assert payload["token_type"] == "bearer"
    assert payload["token"].startswith("tpk_")
    assert payload["api_key"]["name"] == "Embed Production"
    assert payload["api_key"]["scopes"] == ["agents.embed"]

    list_resp = await client.get("/admin/organizations/api-keys", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["key_prefix"] == payload["api_key"]["key_prefix"]
    assert "token" not in items[0]

    revoke_resp = await client.post(
        f"/admin/organizations/api-keys/{payload['api_key']['id']}/revoke",
        headers=headers,
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["api_key"]["status"] == "revoked"


@pytest.mark.asyncio
async def test_api_key_secret_is_only_returned_on_create(client, db_session):
    tenant, owner, org_unit, _ = await seed_admin_tenant_and_agent(db_session)
    headers = await _create_headers(tenant, owner, org_unit)

    create_resp = await client.post(
        "/admin/organizations/api-keys",
        headers=headers,
        json={"name": "One Time Secret", "scopes": ["agents.embed"]},
    )
    assert create_resp.status_code == 201
    token = create_resp.json()["token"]

    list_resp = await client.get("/admin/organizations/api-keys", headers=headers)
    assert list_resp.status_code == 200
    assert token not in str(list_resp.json())
