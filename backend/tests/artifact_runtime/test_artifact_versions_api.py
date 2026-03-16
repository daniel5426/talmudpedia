import uuid

import pytest

from app.api.dependencies import get_current_principal
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from main import app


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="Artifact Tenant", slug=f"artifact-tenant-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"artifact-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Artifact Org",
        slug=f"artifact-org-{uuid.uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    membership = OrgMembership(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add_all([tenant, user, org_unit, membership])
    await db_session.commit()
    return tenant, user


def _override_principal(tenant_id, user):
    async def _inner():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "tenant_id": str(tenant_id),
            "scopes": ["artifacts.read", "artifacts.write"],
            "auth_token": "test-token",
        }

    return _inner


@pytest.mark.asyncio
async def test_artifact_version_endpoints_list_and_get_saved_revisions(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Artifact Versions",
                "description": "version endpoint coverage",
                "kind": "agent_node",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'step': 1}\n"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "config_schema": {},
                "agent_contract": {
                    "state_reads": [],
                    "state_writes": [],
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "node_ui": {},
                },
            },
        )
        assert create_response.status_code == 200, create_response.text
        artifact = create_response.json()

        update_response = await client.put(
            f"/admin/artifacts/{artifact['id']}?tenant_slug={tenant.slug}",
            json={
                "display_name": "Artifact Versions v2",
                "description": "updated version",
                "runtime": {
                    "source_files": [
                        {"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'step': 2}\n"},
                        {"path": "helpers.py", "content": "VALUE = 2\n"},
                    ],
                    "entry_module_path": "main.py",
                    "python_dependencies": ["httpx>=0.27"],
                    "runtime_target": "cloudflare_workers",
                },
                "config_schema": {"type": "object"},
                "agent_contract": {
                    "state_reads": ["messages"],
                    "state_writes": ["tool_outputs"],
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "node_ui": {"title": "V2"},
                },
            },
        )
        assert update_response.status_code == 200, update_response.text

        publish_response = await client.post(
            f"/admin/artifacts/{artifact['id']}/publish?tenant_slug={tenant.slug}",
            json={},
        )
        assert publish_response.status_code == 200, publish_response.text
        published_revision_id = publish_response.json()["revision_id"]

        versions_response = await client.get(f"/admin/artifacts/{artifact['id']}/versions?tenant_slug={tenant.slug}")
        assert versions_response.status_code == 200, versions_response.text
        versions = versions_response.json()

        assert [item["revision_number"] for item in versions] == [2, 1]
        assert versions[0]["id"] == published_revision_id
        assert versions[0]["version_label"] == "v2"
        assert versions[0]["is_current_draft"] is True
        assert versions[0]["is_current_published"] is True
        assert versions[0]["source_file_count"] == 2
        assert versions[1]["is_current_draft"] is False
        assert versions[1]["is_current_published"] is False

        latest_version_response = await client.get(
            f"/admin/artifacts/{artifact['id']}/versions/{published_revision_id}?tenant_slug={tenant.slug}"
        )
        assert latest_version_response.status_code == 200, latest_version_response.text
        latest_version = latest_version_response.json()
        assert latest_version["runtime"]["entry_module_path"] == "main.py"
        assert latest_version["runtime"]["python_dependencies"] == ["httpx>=0.27"]
        assert {item["path"] for item in latest_version["runtime"]["source_files"]} == {"main.py", "helpers.py"}
        assert latest_version["display_name"] == "Artifact Versions v2"

        first_revision_id = versions[1]["id"]
        first_version_response = await client.get(
            f"/admin/artifacts/{artifact['id']}/versions/{first_revision_id}?tenant_slug={tenant.slug}"
        )
        assert first_version_response.status_code == 200, first_version_response.text
        first_version = first_version_response.json()
        assert first_version["version_label"] == "draft"
        assert first_version["runtime"]["python_dependencies"] == []
        assert first_version["runtime"]["source_files"][0]["content"].strip().endswith("{'step': 1}")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
