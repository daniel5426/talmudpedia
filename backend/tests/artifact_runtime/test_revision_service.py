import io
import json
import uuid

import pytest

from app.db.postgres.models.artifact_runtime import ArtifactStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.services.artifact_runtime.bundle_builder import ArtifactBundleBuilder
from app.services.artifact_runtime.cloudflare_package_builder import CloudflareArtifactPackageBuilder
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService


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


@pytest.mark.asyncio
async def test_revision_service_creates_updates_and_publishes_multifile_revisions(db_session):
    tenant, user = await _seed_tenant_context(db_session)

    service = ArtifactRevisionService(db_session)
    artifact = await service.create_artifact(
        tenant_id=tenant.id,
        created_by=user.id,
        slug="reading_time",
        display_name="Reading Time",
        description="Estimate reading time",
        kind="agent_node",
        source_files=[
            {"path": "main.py", "content": "from helpers import answer\n\ndef execute(inputs, config, context):\n    return answer(inputs)\n"},
            {"path": "helpers.py", "content": "def answer(data):\n    return {'echo': data}\n"},
        ],
        entry_module_path="main.py",
        python_dependencies=["requests>=2.0"],
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
    artifact = await ArtifactRegistryService(db_session).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)

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
        python_dependencies=["httpx>=0.27"],
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
    artifact = await ArtifactRegistryService(db_session).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)

    assert artifact.latest_draft_revision.revision_number == 2
    assert artifact.latest_draft_revision.build_hash != first_hash
    assert artifact.latest_draft_revision.entry_module_path == "main.py"
    assert artifact.latest_draft_revision.python_dependencies == ["httpx>=0.27"]
    assert artifact.kind.value == "agent_node"

    published_revision = await service.publish_latest_draft(artifact)
    await db_session.commit()
    artifact = await ArtifactRegistryService(db_session).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)

    assert published_revision.is_published is True
    assert published_revision.version_label == "v2"
    assert artifact.latest_published_revision_id == published_revision.id
    assert artifact.status == ArtifactStatus.PUBLISHED


def test_bundle_builder_hash_is_stable_for_same_revision_payload():
    class _Revision:
        id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        display_name = "Stable"
        description = "Stable bundle"
        kind = "rag_operator"
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
        tenant_id = uuid.uuid4()
        kind = "tool_impl"
        entry_module_path = "main.py"
        python_dependencies = []
        source_files = [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}]
        runtime_target = "cloudflare_workers"

    package = CloudflareArtifactPackageBuilder().build_revision_package(_Revision(), namespace="staging")
    module_names = {module["name"] for module in package.modules}
    main_module = next(module for module in package.modules if module["name"] == "main.py")
    assert "main.py" in module_names
    assert "from main import execute as artifact_execute" in main_module["content"]
    assert "traceback.format_exception" in main_module["content"]
