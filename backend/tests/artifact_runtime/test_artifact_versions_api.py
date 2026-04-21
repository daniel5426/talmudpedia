import uuid
from types import SimpleNamespace

import pytest

from app.api.dependencies import get_current_principal
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Organization, User
from main import app


async def _seed_tenant_context(db_session):
    tenant = Organization(id=uuid.uuid4(), name="Artifact Organization", slug=f"artifact-tenant-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"artifact-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        name="Artifact Org",
        slug=f"artifact-org-{uuid.uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    membership = OrgMembership(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add_all([tenant, user, org_unit, membership])
    await db_session.commit()
    return tenant, user


def _override_principal(organization_id, user):
    async def _inner():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "organization_id": str(organization_id),
            "scopes": ["artifacts.read", "artifacts.write"],
            "auth_token": "test-token",
        }

    return _inner


@pytest.mark.asyncio
async def test_artifact_version_endpoints_list_and_get_saved_revisions(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    async def fake_ensure_deployment(self, *, revision, namespace, organization_id=None):
        return SimpleNamespace(
            worker_name="prod-worker",
            deployment_id="dep-1",
            version_id="ver-1",
            build_hash=revision.build_hash,
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment",
        fake_ensure_deployment,
    )

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
        assert "display_name" not in versions[0]
        assert "runtime" not in versions[0]
        assert "tool_contract" not in versions[0]
        assert versions[1]["is_current_draft"] is False
        assert versions[1]["is_current_published"] is False

        latest_version_response = await client.get(
            f"/admin/artifacts/{artifact['id']}/versions/{published_revision_id}?tenant_slug={tenant.slug}"
        )
        assert latest_version_response.status_code == 200, latest_version_response.text
        latest_version = latest_version_response.json()
        assert latest_version["runtime"]["entry_module_path"] == "main.py"
        assert latest_version["runtime"]["dependencies"] == ["httpx>=0.27"]
        assert {item["path"] for item in latest_version["runtime"]["source_files"]} == {"main.py", "helpers.py"}
        assert latest_version["display_name"] == "Artifact Versions v2"

        first_revision_id = versions[1]["id"]
        first_version_response = await client.get(
            f"/admin/artifacts/{artifact['id']}/versions/{first_revision_id}?tenant_slug={tenant.slug}"
        )
        assert first_version_response.status_code == 200, first_version_response.text
        first_version = first_version_response.json()
        assert first_version["version_label"] == "draft"
        assert first_version["runtime"]["dependencies"] == []
        assert first_version["runtime"]["source_files"][0]["content"].strip().endswith("{'step': 1}")
    finally:
        monkeypatch.undo()
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_duplicate_artifact_creates_tenant_copy_with_incremented_name(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Email Validator",
                "description": "duplicate coverage",
                "kind": "tool_impl",
                "runtime": {
                    "language": "javascript",
                    "source_files": [{"path": "main.js", "content": "export async function execute(inputs, config, context) { return { ok: true } }\n"}],
                    "entry_module_path": "main.js",
                    "dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "config_schema": {},
                "capabilities": {},
                "tool_contract": {
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "side_effects": [],
                    "execution_mode": "sync",
                    "tool_ui": {},
                },
            },
        )
        assert create_response.status_code == 200, create_response.text
        original = create_response.json()

        duplicate_one = await client.post(
            f"/admin/artifacts/{original['id']}/duplicate?tenant_slug={tenant.slug}",
            json={},
        )
        assert duplicate_one.status_code == 200, duplicate_one.text
        first_copy = duplicate_one.json()
        assert first_copy["id"] != original["id"]
        assert first_copy["display_name"] == "Email Validator (1)"
        assert first_copy["kind"] == original["kind"]
        assert first_copy["runtime"]["language"] == "javascript"
        assert first_copy["runtime"]["entry_module_path"] == "main.js"

        duplicate_two = await client.post(
            f"/admin/artifacts/{original['id']}/duplicate?tenant_slug={tenant.slug}",
            json={},
        )
        assert duplicate_two.status_code == 200, duplicate_two.text
        second_copy = duplicate_two.json()
        assert second_copy["display_name"] == "Email Validator (2)"

        list_response = await client.get(f"/admin/artifacts?tenant_slug={tenant.slug}")
        assert list_response.status_code == 200, list_response.text
        names = [item["display_name"] for item in list_response.json()["items"]]
        assert names.count("Email Validator") == 1
        assert "Email Validator (1)" in names
        assert "Email Validator (2)" in names
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_artifact_versions_list_excludes_detail_only_fields(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Multiplier Tool",
                "description": "list payload shape coverage",
                "kind": "tool_impl",
                "runtime": {
                    "language": "javascript",
                    "source_files": [
                        {
                            "path": "main.js",
                            "content": "export async function execute(inputs) { return { product: inputs.a * inputs.b }; }\n",
                        }
                    ],
                    "entry_module_path": "main.js",
                    "dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "config_schema": {"type": "object"},
                "capabilities": {"network_access": False},
                "tool_contract": {
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {"description": "Multiply two numbers together."},
                },
            },
        )
        assert create_response.status_code == 200, create_response.text
        artifact = create_response.json()

        update_response = await client.put(
            f"/admin/artifacts/{artifact['id']}?tenant_slug={tenant.slug}",
            json={
                "description": "updated list payload shape coverage",
                "runtime": {
                    "language": "javascript",
                    "source_files": [
                        {
                            "path": "main.js",
                            "content": "export async function execute(inputs) { return { product: inputs.a * inputs.b * 2 }; }\n",
                        }
                    ],
                    "entry_module_path": "main.js",
                    "dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "tool_contract": {
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {"description": "Multiply two numbers together."},
                },
            },
        )
        assert update_response.status_code == 200, update_response.text

        versions_response = await client.get(f"/admin/artifacts/{artifact['id']}/versions?tenant_slug={tenant.slug}")
        assert versions_response.status_code == 200, versions_response.text
        versions = versions_response.json()

        assert [item["revision_number"] for item in versions] == [2, 1]
        assert versions[0]["source_file_count"] == 1
        assert "display_name" not in versions[0]
        assert "description" not in versions[0]
        assert "kind" not in versions[0]
        assert "runtime" not in versions[0]
        assert "capabilities" not in versions[0]
        assert "tool_contract" not in versions[0]
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_artifact_export_and_import_round_trip_through_transfer_file(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    async def fake_ensure_deployment(self, *, revision, namespace, organization_id=None):
        return SimpleNamespace(
            worker_name="prod-worker",
            deployment_id="dep-1",
            version_id="ver-1",
            build_hash=revision.build_hash,
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment",
        fake_ensure_deployment,
    )

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Portable Artifact",
                "description": "moves between environments",
                "kind": "tool_impl",
                "runtime": {
                    "language": "javascript",
                    "source_files": [{"path": "main.js", "content": "export async function execute(inputs, config, context) { return { ok: inputs.ok ?? true } }\n"}],
                    "entry_module_path": "main.js",
                    "dependencies": ["zod@^3.23.8"],
                    "runtime_target": "cloudflare_workers",
                },
                "config_schema": {"type": "object"},
                "capabilities": {"network_access": False, "allowed_hosts": ["example.com"]},
                "tool_contract": {
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "side_effects": ["http"],
                    "execution_mode": "interactive",
                    "tool_ui": {"title": "Portable"},
                },
            },
        )
        assert create_response.status_code == 200, create_response.text
        artifact = create_response.json()

        publish_response = await client.post(
            f"/admin/artifacts/{artifact['id']}/publish?tenant_slug={tenant.slug}",
            json={},
        )
        assert publish_response.status_code == 200, publish_response.text

        export_response = await client.get(
            f"/admin/artifacts/{artifact['id']}/export?tenant_slug={tenant.slug}",
        )
        assert export_response.status_code == 200, export_response.text
        transfer_file = export_response.json()
        assert transfer_file["format"] == "talmudpedia.artifact"
        assert transfer_file["format_version"] == 1
        assert transfer_file["artifact"]["display_name"] == "Portable Artifact"
        assert transfer_file["artifact"]["published"] is True
        assert transfer_file["artifact"]["runtime"]["dependencies"] == ["zod@^3.23.8"]
        assert transfer_file["artifact"]["runtime"]["source_files"][0]["path"] == "main.js"

        import_response = await client.post(
            f"/admin/artifacts/import?tenant_slug={tenant.slug}",
            json=transfer_file,
        )
        assert import_response.status_code == 200, import_response.text
        imported = import_response.json()
        assert imported["source_published"] is True
        assert imported["artifact"]["id"] != artifact["id"]
        assert imported["artifact"]["display_name"] == "Portable Artifact (1)"
        assert imported["artifact"]["type"] == "draft"
        assert imported["artifact"]["runtime"]["language"] == "javascript"
        assert imported["artifact"]["runtime"]["dependencies"] == ["zod@^3.23.8"]
        assert imported["artifact"]["tool_contract"]["tool_ui"]["title"] == "Portable"
    finally:
        monkeypatch.undo()
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_update_artifact_returns_clean_python_syntax_error(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Syntax Error Save",
                "description": "save validation boundary",
                "kind": "tool_impl",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "config_schema": {"type": "object"},
                "capabilities": {"network_access": False},
                "tool_contract": {
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {},
                },
            },
        )
        assert create_response.status_code == 200, create_response.text
        artifact = create_response.json()

        update_response = await client.put(
            f"/admin/artifacts/{artifact['id']}?tenant_slug={tenant.slug}",
            json={
                "runtime": {
                    "source_files": [
                        {
                            "path": "main.py",
                            "content": "export async function execute(inputs, config, context) { return { ok: true }; }\n",
                        }
                    ],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
            },
        )
        assert update_response.status_code == 422, update_response.text
        assert update_response.json()["detail"] == {
            "code": "VALIDATION_ERROR",
            "message": "Invalid Python source in `main.py`: invalid syntax",
            "http_status": 422,
            "retryable": False,
        }
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
