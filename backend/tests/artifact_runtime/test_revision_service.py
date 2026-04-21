import io
import json
import uuid

import pytest
from sqlalchemy import func, select

from app.db.postgres.models.artifact_runtime import ArtifactRevision, ArtifactStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.services.artifact_runtime.bundle_builder import ArtifactBundleBuilder
from app.services.artifact_runtime.cloudflare_package_builder import CloudflareArtifactPackageBuilder
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from app.services.artifact_runtime.workers_validation import ArtifactWorkersCompatibilityError
from app.services.security_bootstrap_service import SecurityBootstrapService


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
    db_session.add_all([tenant, user, org_unit, membership])
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(
        organization_id=tenant.id,
        user_id=user.id,
        assigned_by=user.id,
    )
    await db_session.commit()
    return tenant, user


@pytest.mark.asyncio
async def test_revision_service_creates_updates_and_publishes_multifile_revisions(db_session):
    tenant, user = await _seed_tenant_context(db_session)

    service = ArtifactRevisionService(db_session)
    artifact = await service.create_artifact(
        organization_id=tenant.id,
        created_by=user.id,
        display_name="Reading Time",
        description="Estimate reading time",
        kind="agent_node",
        language="python",
        source_files=[
            {"path": "main.py", "content": "from helpers import answer\n\ndef execute(inputs, config, context):\n    return answer(inputs)\n"},
            {"path": "helpers.py", "content": "def answer(data):\n    return {'echo': data}\n"},
        ],
        entry_module_path="main.py",
        dependencies=["requests>=2.0"],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": False},
        config_schema={"type": "object", "properties": {"enabled": {"type": "boolean", "default": True}}},
        agent_contract={
            "state_reads": ["messages"],
            "state_writes": ["tool_outputs"],
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"echo": {"type": "object"}}},
            "node_ui": {"icon": "Sparkles"},
        },
    )
    await db_session.commit()
    artifact = await ArtifactRegistryService(db_session).get_organization_artifact(artifact_id=artifact.id, organization_id=tenant.id)

    assert artifact.latest_draft_revision_id is not None
    assert artifact.status == ArtifactStatus.DRAFT
    assert artifact.latest_published_revision_id is None
    assert artifact.latest_draft_revision.source_files[0]["path"] == "main.py"
    assert artifact.latest_draft_revision.entry_module_path == "main.py"
    assert artifact.latest_draft_revision.python_dependencies == ["requests>=2.0"]
    first_hash = artifact.latest_draft_revision.build_hash

    await service.update_artifact(
        artifact,
        updated_by=user.id,
        display_name="Reading Time v2",
        description="Estimate reading time better",
        source_files=[
            {"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'updated': True, 'echo': inputs}\n"},
        ],
        entry_module_path="main.py",
        language="python",
        dependencies=["httpx>=0.27"],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": True},
        config_schema={"type": "object", "properties": {"wpm": {"type": "integer", "default": 200}}},
        agent_contract={
            "state_reads": ["state"],
            "state_writes": ["tool_outputs"],
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"updated": {"type": "boolean"}}},
            "node_ui": {"icon": "Clock3"},
        },
    )
    await db_session.commit()
    artifact = await ArtifactRegistryService(db_session).get_organization_artifact(artifact_id=artifact.id, organization_id=tenant.id)

    assert artifact.latest_draft_revision.revision_number == 2
    assert artifact.latest_draft_revision.build_hash != first_hash
    assert artifact.latest_draft_revision.entry_module_path == "main.py"
    assert artifact.latest_draft_revision.python_dependencies == ["httpx>=0.27"]
    assert artifact.kind.value == "agent_node"

    published_revision = await service.publish_latest_draft(artifact)
    await db_session.commit()
    artifact = await ArtifactRegistryService(db_session).get_organization_artifact(artifact_id=artifact.id, organization_id=tenant.id)

    assert published_revision.is_published is True
    assert published_revision.version_label == "v2"
    assert artifact.latest_published_revision_id == published_revision.id
    assert artifact.status == ArtifactStatus.PUBLISHED


@pytest.mark.asyncio
async def test_revision_service_does_not_create_new_revision_for_noop_update(db_session):
    tenant, user = await _seed_tenant_context(db_session)

    service = ArtifactRevisionService(db_session)
    artifact = await service.create_artifact(
        organization_id=tenant.id,
        created_by=user.id,
        display_name="Noop Revision",
        description="unchanged",
        kind="agent_node",
        language="python",
        source_files=[
            {"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"},
        ],
        entry_module_path="main.py",
        dependencies=["requests>=2.0"],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": False},
        config_schema={"type": "object"},
        agent_contract={
            "state_reads": [],
            "state_writes": [],
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "node_ui": {},
        },
    )
    await db_session.commit()
    artifact = await ArtifactRegistryService(db_session).get_organization_artifact(artifact_id=artifact.id, organization_id=tenant.id)
    assert artifact.latest_draft_revision is not None
    original_revision_id = artifact.latest_draft_revision.id
    original_revision_number = artifact.latest_draft_revision.revision_number

    returned_revision = await service.update_artifact(
        artifact,
        updated_by=user.id,
        display_name="Noop Revision",
        description="unchanged",
        source_files=[{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}],
        entry_module_path="main.py",
        language="python",
        dependencies=["requests>=2.0"],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": False},
        config_schema={"type": "object"},
        agent_contract={
            "state_reads": [],
            "state_writes": [],
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "node_ui": {},
        },
    )
    await db_session.commit()
    artifact = await ArtifactRegistryService(db_session).get_organization_artifact(artifact_id=artifact.id, organization_id=tenant.id)
    revision_count = await db_session.scalar(
        select(func.count()).select_from(ArtifactRevision).where(ArtifactRevision.artifact_id == artifact.id)
    )

    assert returned_revision.id == original_revision_id
    assert artifact.latest_draft_revision_id == original_revision_id
    assert artifact.latest_draft_revision.revision_number == original_revision_number
    assert int(revision_count or 0) == 1


@pytest.mark.asyncio
async def test_revision_service_rejects_language_mutation_for_persisted_artifact(db_session):
    tenant, user = await _seed_tenant_context(db_session)

    service = ArtifactRevisionService(db_session)
    artifact = await service.create_artifact(
        organization_id=tenant.id,
        created_by=user.id,
        display_name="Immutable Language",
        description="language lock",
        kind="tool_impl",
        language="python",
        source_files=[{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}],
        entry_module_path="main.py",
        dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": False},
        config_schema={"type": "object"},
        tool_contract={
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "side_effects": [],
            "execution_mode": "interactive",
            "tool_ui": {},
        },
    )
    await db_session.commit()
    artifact = await ArtifactRegistryService(db_session).get_organization_artifact(artifact_id=artifact.id, organization_id=tenant.id)

    with pytest.raises(ValueError, match="Artifact language is immutable"):
        await service.update_artifact(
            artifact,
            updated_by=user.id,
            display_name="Immutable Language",
            description="language lock",
            source_files=[{"path": "main.js", "content": "export async function execute(inputs, config, context) { return { ok: true }; }\n"}],
            entry_module_path="main.js",
            language="javascript",
            dependencies=[],
            runtime_target="cloudflare_workers",
            capabilities={"network_access": False},
            config_schema={"type": "object"},
            tool_contract={
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "side_effects": [],
                "execution_mode": "interactive",
                "tool_ui": {},
            },
        )


@pytest.mark.asyncio
async def test_publish_latest_draft_rejects_missing_python_execute_handler(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    service = ArtifactRevisionService(db_session)
    artifact = await service.create_artifact(
        organization_id=tenant.id,
        created_by=user.id,
        display_name="Broken Python Publish",
        description="missing execute",
        kind="tool_impl",
        language="python",
        source_files=[{"path": "main.py", "content": "def helper():\n    return {'ok': True}\n"}],
        entry_module_path="main.py",
        dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": False},
        config_schema={"type": "object"},
        tool_contract={
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "side_effects": [],
            "execution_mode": "interactive",
            "tool_ui": {},
        },
    )

    with pytest.raises(ValueError, match=r"Artifact entry module main\.py must define execute\(inputs, config, context\)"):
        await service.publish_latest_draft(artifact)


@pytest.mark.asyncio
async def test_publish_latest_draft_rejects_unexported_javascript_execute_handler(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    service = ArtifactRevisionService(db_session)
    artifact = await service.create_artifact(
        organization_id=tenant.id,
        created_by=user.id,
        display_name="Broken JS Publish",
        description="missing export",
        kind="tool_impl",
        language="javascript",
        source_files=[{"path": "main.js", "content": "async function execute(inputs, config, context) { return { ok: true }; }\n"}],
        entry_module_path="main.js",
        dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": False},
        config_schema={"type": "object"},
        tool_contract={
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "side_effects": [],
            "execution_mode": "interactive",
            "tool_ui": {},
        },
    )

    with pytest.raises(ValueError, match=r"Artifact entry module main\.js must export execute\(inputs, config, context\)"):
        await service.publish_latest_draft(artifact)


def test_bundle_builder_hash_is_stable_for_same_revision_payload():
    class _Revision:
        id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        organization_id = uuid.uuid4()
        display_name = "Stable"
        description = "Stable bundle"
        kind = "rag_operator"
        language = "python"
        input_type = "raw_documents"
        output_type = "raw_documents"
        python_dependencies = ["requests>=2.0"]
        runtime_target = "cloudflare_workers"
        capabilities = {}
        config_schema = {}
        agent_contract = None
        rag_contract = {"operator_category": "transform", "pipeline_role": "ingestion", "input_schema": {}, "output_schema": {}}
        tool_contract = None
        version_label = "draft"
        is_published = False
        is_ephemeral = False
        entry_module_path = "main.py"
        source_files = [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}]

    builder = ArtifactBundleBuilder()
    first = builder.build_revision_bundle(_Revision())
    second = builder.build_revision_bundle(_Revision())
    assert first.bundle_hash == second.bundle_hash
    assert first.payload == second.payload
    assert first.dependency_hash == second.dependency_hash

    manifest = json.loads(io.BytesIO(first.payload).getvalue().decode("utf-8"))
    assert manifest["entry_module_path"] == "main.py"
    assert manifest["source_files"][0]["path"] == "main.py"


def test_cloudflare_package_builder_emits_runtime_main_wrapper():
    class _Revision:
        id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        organization_id = uuid.uuid4()
        kind = "tool_impl"
        language = "python"
        entry_module_path = "main.py"
        python_dependencies = []
        manifest_json = {}
        source_files = [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}]
        runtime_target = "cloudflare_workers"

    package = CloudflareArtifactPackageBuilder().build_revision_package(_Revision(), namespace="staging")
    module_names = {module["name"] for module in package.modules}
    main_module = next(module for module in package.modules if module["name"] == "__artifact_bootstrap.py")
    assert "__artifact_bootstrap.py" in module_names
    assert 'importlib.import_module("main")' in main_module["content"]
    assert "traceback.format_exception" in main_module["content"]


def test_cloudflare_package_builder_records_declared_python_dependencies():
    class _Revision:
        id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        organization_id = uuid.uuid4()
        kind = "tool_impl"
        language = "python"
        entry_module_path = "main.py"
        python_dependencies = ["openai"]
        manifest_json = {}
        source_files = [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}]
        runtime_target = "cloudflare_workers"

    package = CloudflareArtifactPackageBuilder().build_revision_package(_Revision(), namespace="staging")
    assert package.metadata["dependency_manifest"]["declared"] == ["openai"]


def test_cloudflare_package_builder_allows_neutral_files_and_keeps_mismatched_code_as_text():
    class _Revision:
        id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        organization_id = uuid.uuid4()
        kind = "tool_impl"
        language = "javascript"
        entry_module_path = "main.js"
        python_dependencies = []
        manifest_json = {}
        source_files = [
            {"path": "main.js", "content": "export async function execute(inputs, config, context) { return { ok: true }; }\n"},
            {"path": "notes.txt", "content": "hello"},
            {"path": "config.json", "content": "{\"ok\":true}"},
            {"path": "helper.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"},
        ]
        runtime_target = "cloudflare_workers"

    package = CloudflareArtifactPackageBuilder().build_revision_package(_Revision(), namespace="staging")
    module_by_name = {module["name"]: module for module in package.modules}

    assert module_by_name["src/artifact/main.js"]["type"] == "esm"
    assert module_by_name["src/artifact/notes.txt"]["type"] == "text"
    assert module_by_name["src/artifact/config.json"]["type"] == "text"
    assert module_by_name["src/artifact/helper.py"]["type"] == "text"


def test_cloudflare_python_package_builder_materializes_runtime_source_tree_for_assets():
    class _Revision:
        id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        organization_id = uuid.uuid4()
        kind = "tool_impl"
        language = "python"
        entry_module_path = "main.py"
        python_dependencies = []
        manifest_json = {}
        source_files = [
            {
                "path": "main.py",
                "content": (
                    "from pathlib import Path\n\n"
                    "def execute(inputs, config, context):\n"
                    "    return {'config': Path('config.json').read_text()}\n"
                ),
            },
            {"path": "config.json", "content": '{"ok": true}'},
        ]
        runtime_target = "cloudflare_workers"

    package = CloudflareArtifactPackageBuilder().build_revision_package(_Revision(), namespace="staging")
    bootstrap = next(module for module in package.modules if module["name"] == "__artifact_bootstrap.py")["content"]

    assert "_materialize_source_tree(source_files)" in bootstrap
    assert 'payload.get("source_files")' in bootstrap
    assert 'Path("config.json").read_text()' not in bootstrap
    assert "shutil.rmtree(temp_root, ignore_errors=True)" in bootstrap


def test_cloudflare_package_builder_rejects_entry_module_that_does_not_match_language_lane():
    class _Revision:
        id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        organization_id = uuid.uuid4()
        kind = "tool_impl"
        language = "javascript"
        entry_module_path = "main.py"
        python_dependencies = []
        manifest_json = {}
        source_files = [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}]
        runtime_target = "cloudflare_workers"

    with pytest.raises(ArtifactWorkersCompatibilityError, match="JavaScript Workers artifacts must use a JS/TS entry module"):
        CloudflareArtifactPackageBuilder().build_revision_package(_Revision(), namespace="staging")


@pytest.mark.asyncio
async def test_revision_service_rejects_unsupported_credential_usage_on_save(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    credential = IntegrationCredential(
        organization_id=tenant.id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        display_name="OpenAI Runtime",
        credentials={"api_key": "super-secret-key"},
        is_enabled=True,
        is_default=True,
    )
    db_session.add(credential)
    await db_session.commit()

    with pytest.raises(ValueError, match="Only exact string-literal values"):
        await ArtifactRevisionService(db_session).create_artifact(
            organization_id=tenant.id,
            created_by=user.id,
            display_name="Bad Credential Artifact",
            description=None,
            kind="tool_impl",
            language="python",
            source_files=[{"path": "main.py", "content": f'def execute(inputs, config, context):\n    return {{"auth": "Bearer @{{{credential.id}}}"}}\n'}],
            entry_module_path="main.py",
            dependencies=[],
            runtime_target="cloudflare_workers",
            capabilities={"network_access": True},
            config_schema={},
            tool_contract={"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}},
        )
