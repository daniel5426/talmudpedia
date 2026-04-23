import uuid

import pytest
from sqlalchemy import select

from app.api.dependencies import get_current_principal
from app.db.postgres.models.artifact_runtime import ArtifactCodingSession, ArtifactCodingSharedDraft
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry, ModelStatus
from app.db.postgres.models.workspace import Project
from app.services.artifact_coding_agent_profile import ensure_artifact_coding_agent_profile
from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.services.security_bootstrap_service import SecurityBootstrapService
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
        status=MembershipStatus.active,
    )
    project = Project(
        id=uuid.uuid4(),
        organization_id=tenant.id,
        name="Artifact Project",
        slug=f"artifact-project-{uuid.uuid4().hex[:8]}",
        is_default=True,
        created_by=user.id,
    )
    existing_model = await db_session.scalar(
        select(ModelRegistry).where(
            ModelRegistry.organization_id.is_(None),
            ModelRegistry.capability_type == ModelCapabilityType.CHAT,
            ModelRegistry.is_active.is_(True),
            ModelRegistry.is_default.is_(True),
        )
    )
    db_session.add_all([tenant, user, org_unit, membership, project])
    if existing_model is None:
        db_session.add(
            ModelRegistry(
                organization_id=None,
                name="Artifact Working Draft Test Model",
                capability_type=ModelCapabilityType.CHAT,
                status=ModelStatus.ACTIVE,
                is_active=True,
                is_default=True,
            )
        )
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(
        organization_id=tenant.id,
        user_id=user.id,
        assigned_by=user.id,
    )
    await db_session.commit()
    return tenant, user, project


def _override_principal(organization_id, project_id, user):
    async def _inner():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "organization_id": str(organization_id),
            "project_id": str(project_id),
            "scopes": ["artifacts.read", "artifacts.write"],
            "auth_token": "test-token",
        }

    return _inner


@pytest.mark.asyncio
async def test_artifact_working_draft_endpoints_persist_unsaved_snapshot(client, db_session):
    tenant, user, project = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, project.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Artifact Working Draft",
                "description": "working draft coverage",
                "kind": "agent_node",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'step': 1}\n"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": ["requests>=2.0"],
                    "runtime_target": "cloudflare_workers",
                },
                "capabilities": {"network_access": False, "allowed_hosts": [], "secret_refs": [], "storage_access": [], "side_effects": []},
                "config_schema": {"type": "object"},
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

        initial_response = await client.get(f"/admin/artifacts/{artifact['id']}/working-draft?tenant_slug={tenant.slug}")
        assert initial_response.status_code == 200, initial_response.text
        initial_draft = initial_response.json()
        assert initial_draft["artifact_id"] == artifact["id"]
        assert initial_draft["draft_snapshot"]["display_name"] == "Artifact Working Draft"

        update_response = await client.put(
            f"/admin/artifacts/{artifact['id']}/working-draft?tenant_slug={tenant.slug}",
            json={
                "artifact_id": artifact["id"],
                "draft_key": "draft-key-1",
                "draft_snapshot": {
                    "display_name": "Artifact Working Draft Unsaved",
                    "description": "unsaved change",
                    "kind": "agent_node",
                    "source_files": [
                        {"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'step': 2}\n"},
                        {"path": "helpers.py", "content": "VALUE = 2\n"},
                    ],
                    "entry_module_path": "main.py",
                    "python_dependencies": "httpx>=0.27",
                    "runtime_target": "cloudflare_workers",
                    "capabilities": "{\"network_access\": false, \"allowed_hosts\": [], \"secret_refs\": [], \"storage_access\": [], \"side_effects\": []}",
                    "config_schema": "{\"type\": \"object\", \"properties\": {\"enabled\": {\"type\": \"boolean\"}}}",
                    "agent_contract": "{\"state_reads\": [\"messages\"], \"state_writes\": [], \"input_schema\": {\"type\": \"object\"}, \"output_schema\": {\"type\": \"object\"}, \"node_ui\": {}}",
                },
            },
        )
        assert update_response.status_code == 200, update_response.text

        persisted_response = await client.get(f"/admin/artifacts/{artifact['id']}/working-draft?tenant_slug={tenant.slug}")
        assert persisted_response.status_code == 200, persisted_response.text
        persisted_draft = persisted_response.json()
        assert persisted_draft["draft_snapshot"]["display_name"] == "Artifact Working Draft Unsaved"
        assert persisted_draft["draft_snapshot"]["description"] == "unsaved change"
        assert persisted_draft["draft_snapshot"]["dependencies"] == "httpx>=0.27"
        assert len(persisted_draft["draft_snapshot"]["source_files"]) == 2
        assert persisted_draft["draft_snapshot"]["source_files"][1]["path"] == "helpers.py"
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_artifact_working_draft_update_keeps_artifact_scope_isolated_from_draft_key_scope(client, db_session):
    tenant, user, project = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, project.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Artifact Working Draft Merge",
                "description": "working draft merge coverage",
                "kind": "tool_impl",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'step': 1}\n"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "capabilities": {"network_access": False, "allowed_hosts": [], "secret_refs": [], "storage_access": [], "side_effects": []},
                "config_schema": {"type": "object"},
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

        initial_response = await client.get(f"/admin/artifacts/{artifact['id']}/working-draft?tenant_slug={tenant.slug}")
        assert initial_response.status_code == 200, initial_response.text

        draft_key = f"draft-{uuid.uuid4().hex[:8]}"
        await ArtifactCodingSharedDraftService(db_session).get_or_create_for_scope(
            organization_id=tenant.id,
            project_id=project.id,
            artifact_id=None,
            draft_key=draft_key,
            initial_snapshot={
                "display_name": "Artifact Working Draft Merge",
                "description": "draft-key row",
                "kind": "tool_impl",
                "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'draft_key': true}\n"}],
                "entry_module_path": "main.py",
                "python_dependencies": "",
                "runtime_target": "cloudflare_workers",
                "capabilities": "{}",
                "config_schema": "{}",
                "tool_contract": "{}",
            },
        )
        await db_session.commit()

        seed_response = await client.put(
            f"/admin/artifacts/{artifact['id']}/working-draft?tenant_slug={tenant.slug}",
            json={
                "artifact_id": artifact["id"],
                "draft_key": draft_key,
                "draft_snapshot": {
                    "display_name": "Artifact Working Draft Merge",
                    "description": "artifact-scoped update",
                    "kind": "tool_impl",
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'step': 2}\n"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": "",
                    "runtime_target": "cloudflare_workers",
                    "capabilities": "{\"network_access\": false, \"allowed_hosts\": [], \"secret_refs\": [], \"storage_access\": [], \"side_effects\": []}",
                    "config_schema": "{\"type\": \"object\"}",
                    "tool_contract": "{\"input_schema\": {\"type\": \"object\"}, \"output_schema\": {\"type\": \"object\"}, \"side_effects\": [], \"execution_mode\": \"interactive\", \"tool_ui\": {}}",
                },
            },
        )
        assert seed_response.status_code == 200, seed_response.text
        assert seed_response.json()["draft_key"] is None

        rows = (
            await db_session.execute(
                select(ArtifactCodingSharedDraft).where(
                    ArtifactCodingSharedDraft.organization_id == tenant.id,
                    ArtifactCodingSharedDraft.project_id == project.id,
                )
            )
        ).scalars().all()
        assert len(rows) == 2

        artifact_row = next(item for item in rows if item.artifact_id == uuid.UUID(artifact["id"]))
        draft_key_row = next(item for item in rows if item.draft_key == draft_key)

        assert artifact_row.draft_key is None
        assert artifact_row.working_draft_snapshot["description"] == "artifact-scoped update"
        assert draft_key_row.artifact_id is None
        assert draft_key_row.working_draft_snapshot["description"] == "draft-key row"
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_artifact_create_links_existing_coding_sessions_by_draft_key(client, db_session):
    tenant, user, project = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, project.id, user)

    try:
        draft_key = f"draft-{uuid.uuid4().hex[:8]}"
        agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, project_id=project.id, actor_user_id=user.id)
        runtime = ArtifactCodingRuntimeService(db_session)
        prepared = await runtime.prepare_session(
            organization_id=tenant.id,
            project_id=project.id,
            user_id=user.id,
            agent_id=agent.id,
            title_prompt="Create artifact from coding session",
            artifact_id=None,
            draft_key=draft_key,
            chat_session_id=None,
            draft_snapshot=runtime.build_initial_snapshot_from_seed(
                {
                    "kind": "tool_impl",
                    "display_name": "Linked History Tool",
                }
            ),
            replace_snapshot=True,
        )
        await db_session.commit()

        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Linked History Tool",
                "description": "links draft sessions on save",
                "draft_key": draft_key,
                "kind": "tool_impl",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return inputs\n"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "capabilities": {"network_access": False, "allowed_hosts": [], "secret_refs": [], "storage_access": [], "side_effects": []},
                "config_schema": {"type": "object"},
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

        sessions_response = await client.get(
            f"/admin/artifacts/coding-agent/v1/sessions?tenant_slug={tenant.slug}&artifact_id={artifact['id']}",
        )
        assert sessions_response.status_code == 200, sessions_response.text
        payload = sessions_response.json()
        assert [item["id"] for item in payload] == [str(prepared.session.id)]

        session = await db_session.get(ArtifactCodingSession, prepared.session.id)
        assert session is not None
        assert str(session.artifact_id) == artifact["id"]
        assert str(session.linked_artifact_id) == artifact["id"]

        shared_rows = (
            await db_session.execute(
                select(ArtifactCodingSharedDraft).where(
                    ArtifactCodingSharedDraft.organization_id == tenant.id,
                    ArtifactCodingSharedDraft.project_id == project.id,
                )
            )
        ).scalars().all()
        linked_row = next(item for item in shared_rows if item.draft_key == draft_key)
        assert str(linked_row.artifact_id) == artifact["id"]
        assert str(linked_row.linked_artifact_id) == artifact["id"]
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_artifact_working_draft_rejects_wrapped_tool_contract(client, db_session):
    tenant, user, project = await _seed_tenant_context(db_session)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, project.id, user)

    try:
        create_response = await client.post(
            f"/admin/artifacts?tenant_slug={tenant.slug}",
            json={
                "display_name": "Wrapped Contract Draft",
                "description": "strict contract shape",
                "kind": "tool_impl",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return inputs\n"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "capabilities": {"network_access": False, "allowed_hosts": [], "secret_refs": [], "storage_access": [], "side_effects": []},
                "config_schema": {"type": "object"},
                "tool_contract": {
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {},
                },
            },
        )
        artifact = create_response.json()

        update_response = await client.put(
            f"/admin/artifacts/{artifact['id']}/working-draft?tenant_slug={tenant.slug}",
            json={
                "artifact_id": artifact["id"],
                "draft_snapshot": {
                    "display_name": "Wrapped Contract Draft",
                    "description": "bad draft",
                    "kind": "tool_impl",
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return inputs\n"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": "",
                    "runtime_target": "cloudflare_workers",
                    "capabilities": "{\"network_access\": false, \"allowed_hosts\": [], \"secret_refs\": [], \"storage_access\": [], \"side_effects\": []}",
                    "config_schema": "{\"type\": \"object\"}",
                    "tool_contract": "{\"tool_contract\": {\"input_schema\": {\"type\": \"object\"}, \"output_schema\": {\"type\": \"object\"}}}",
                },
            },
        )
        assert update_response.status_code == 400, update_response.text
        assert "inner tool contract object" in update_response.text
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
