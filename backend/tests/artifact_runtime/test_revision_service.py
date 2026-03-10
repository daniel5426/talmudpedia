import os
import uuid

import pytest

from app.db.postgres.models.artifact_runtime import ArtifactStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.services.artifact_runtime.bundle_builder import ArtifactBundleBuilder
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
async def test_revision_service_creates_updates_and_publishes_with_bundle_inline(db_session, monkeypatch):
    monkeypatch.delenv("ARTIFACT_BUNDLE_BUCKET", raising=False)
    monkeypatch.delenv("APPS_BUNDLE_BUCKET", raising=False)
    tenant, user = await _seed_tenant_context(db_session)

    service = ArtifactRevisionService(db_session)
    artifact = await service.create_artifact(
        tenant_id=tenant.id,
        created_by=user.id,
        name="reading_time",
        display_name="Reading Time",
        description="Estimate reading time",
        category="custom",
        scope="agent",
        input_type="any",
        output_type="any",
        source_code="def execute(context):\n    return {'echo': context.input_data, 'cfg': context.config}\n",
        config_schema=[{"name": "enabled", "type": "boolean", "default": True}],
        inputs=[{"name": "text", "type": "string"}],
        outputs=[{"name": "echo", "type": "object"}],
        reads=["messages"],
        writes=["tool_outputs"],
    )
    await db_session.commit()
    artifact = await ArtifactRegistryService(db_session).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)

    assert artifact.latest_draft_revision_id is not None
    assert artifact.status == ArtifactStatus.DRAFT
    assert artifact.latest_published_revision_id is None
    assert artifact.latest_draft_revision.bundle_inline_bytes is not None
    first_hash = artifact.latest_draft_revision.bundle_hash

    await service.update_artifact(
        artifact,
        updated_by=user.id,
        display_name="Reading Time v2",
        description="Estimate reading time better",
        category="custom",
        scope="tool",
        input_type="any",
        output_type="any",
        source_code="def execute(context):\n    return {'updated': True, 'echo': context.input_data}\n",
        config_schema=[{"name": "wpm", "type": "integer", "default": 200}],
        inputs=[{"name": "text", "type": "string"}],
        outputs=[{"name": "updated", "type": "boolean"}],
        reads=["state"],
        writes=["tool_outputs"],
    )
    await db_session.commit()
    artifact = await ArtifactRegistryService(db_session).get_tenant_artifact(artifact_id=artifact.id, tenant_id=tenant.id)

    assert artifact.latest_draft_revision.revision_number == 2
    assert artifact.latest_draft_revision.bundle_hash != first_hash
    assert artifact.latest_draft_revision.bundle_inline_bytes is not None

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
        category = "custom"
        scope = "rag"
        input_type = "raw_documents"
        output_type = "raw_documents"
        config_schema = []
        inputs = []
        outputs = []
        reads = []
        writes = []
        version_label = "draft"
        is_published = False
        is_ephemeral = False
        source_code = "def execute(context):\n    return {'ok': True}\n"

    builder = ArtifactBundleBuilder()
    first = builder.build_revision_bundle(_Revision())
    second = builder.build_revision_bundle(_Revision())
    assert first.bundle_hash == second.bundle_hash
    assert first.payload == second.payload
