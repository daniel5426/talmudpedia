from uuid import uuid4

import pytest

from app.db.postgres.models.artifact_runtime import ArtifactRun, ArtifactRunDomain, ArtifactRunStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.services.artifact_runtime.outbound_auth_service import (
    ArtifactOutboundAuthError,
    extract_credential_ids_from_source_files,
    mint_outbound_grant,
    resolve_injected_headers,
)
from app.services.artifact_runtime.revision_service import ArtifactRevisionService


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid4(), name="Outbound Tenant", slug=f"outbound-{uuid4().hex[:8]}")
    user = User(id=uuid4(), email=f"outbound-{uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid4(),
        tenant_id=tenant.id,
        name="Outbound Org",
        slug=f"outbound-org-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    membership = OrgMembership(
        id=uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add_all([tenant, user, org_unit, membership])
    await db_session.commit()
    return tenant, user


def _credential_ref(credential: IntegrationCredential) -> str:
    return f"@{{{credential.id}}}"


@pytest.mark.asyncio
async def test_extract_credential_ids_from_source_files_returns_unique_ids():
    first_id = uuid4()
    second_id = uuid4()
    ids = extract_credential_ids_from_source_files(
        [
            {"path": "main.py", "content": f'credential = "@{{{first_id}}}"\nother = "@{{{second_id}}}"\nagain = "@{{{first_id}}}"'},
        ]
    )

    assert {str(item) for item in ids} == {str(first_id), str(second_id)}


@pytest.mark.asyncio
async def test_resolve_injected_headers_uses_referenced_credential_id(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    credential = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        display_name="OpenAI Explicit",
        credentials={"api_key": "explicit-key"},
        is_enabled=True,
        is_default=True,
    )
    db_session.add(credential)
    await db_session.flush()

    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        tenant_id=tenant.id,
        created_by=user.id,
        display_name="Bound Artifact",
        description=None,
        kind="tool_impl",
        source_files=[{"path": "main.py", "content": f'def execute(inputs, config, context):\n    return {{"credential": "{_credential_ref(credential)}"}}\n'}],
        entry_module_path="main.py",
        python_dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": True},
        config_schema={},
        tool_contract={"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}},
    )
    await db_session.flush()

    run = ArtifactRun(
        tenant_id=tenant.id,
        artifact_id=artifact.id,
        revision_id=artifact.latest_draft_revision_id,
        domain=ArtifactRunDomain.TOOL,
        status=ArtifactRunStatus.RUNNING,
        queue_class="artifact_prod_interactive",
        sandbox_backend="cloudflare_workers",
        input_payload={},
        config_payload={},
        context_payload={},
        runtime_metadata={},
    )
    db_session.add(run)
    await db_session.commit()

    grant = mint_outbound_grant(run=run, revision=artifact.latest_draft_revision)
    headers = await resolve_injected_headers(
        db=db_session,
        grant=grant,
        credential_id=_credential_ref(credential),
        url="https://api.openai.com/v1/chat/completions",
    )

    assert headers == {"Authorization": "Bearer explicit-key"}


@pytest.mark.asyncio
async def test_resolve_injected_headers_rejects_wrong_host(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    credential = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        display_name="OpenAI Explicit",
        credentials={"api_key": "explicit-key"},
        is_enabled=True,
        is_default=True,
    )
    db_session.add(credential)
    await db_session.flush()

    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        tenant_id=tenant.id,
        created_by=user.id,
        display_name="Host Locked Artifact",
        description=None,
        kind="tool_impl",
        source_files=[{"path": "main.py", "content": f'def execute(inputs, config, context):\n    return {{"credential": "{_credential_ref(credential)}"}}\n'}],
        entry_module_path="main.py",
        python_dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": True},
        config_schema={},
        tool_contract={"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}},
    )
    await db_session.flush()

    run = ArtifactRun(
        tenant_id=tenant.id,
        artifact_id=artifact.id,
        revision_id=artifact.latest_draft_revision_id,
        domain=ArtifactRunDomain.TOOL,
        status=ArtifactRunStatus.RUNNING,
        queue_class="artifact_prod_interactive",
        sandbox_backend="cloudflare_workers",
        input_payload={},
        config_payload={},
        context_payload={},
        runtime_metadata={},
    )
    db_session.add(run)
    await db_session.commit()

    grant = mint_outbound_grant(run=run, revision=artifact.latest_draft_revision)
    with pytest.raises(ArtifactOutboundAuthError, match="allowed"):
        await resolve_injected_headers(
            db=db_session,
            grant=grant,
            credential_id=_credential_ref(credential),
            url="https://malicious.example/v1/chat/completions",
        )


@pytest.mark.asyncio
async def test_resolve_injected_headers_rejects_unreferenced_credential(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    first = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        display_name="OpenAI Explicit",
        credentials={"api_key": "explicit-key"},
        is_enabled=True,
        is_default=True,
    )
    second = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.TOOL_PROVIDER,
        provider_key="serper",
        display_name="Serper Explicit",
        credentials={"api_key": "serper-key"},
        is_enabled=True,
        is_default=False,
    )
    db_session.add_all([first, second])
    await db_session.flush()

    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        tenant_id=tenant.id,
        created_by=user.id,
        display_name="Scoped Artifact",
        description=None,
        kind="tool_impl",
        source_files=[{"path": "main.py", "content": f'def execute(inputs, config, context):\n    return {{"credential": "{_credential_ref(first)}"}}\n'}],
        entry_module_path="main.py",
        python_dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": True},
        config_schema={},
        tool_contract={"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}},
    )
    await db_session.flush()

    run = ArtifactRun(
        tenant_id=tenant.id,
        artifact_id=artifact.id,
        revision_id=artifact.latest_draft_revision_id,
        domain=ArtifactRunDomain.TOOL,
        status=ArtifactRunStatus.RUNNING,
        queue_class="artifact_prod_interactive",
        sandbox_backend="cloudflare_workers",
        input_payload={},
        config_payload={},
        context_payload={},
        runtime_metadata={},
    )
    db_session.add(run)
    await db_session.commit()

    grant = mint_outbound_grant(run=run, revision=artifact.latest_draft_revision)
    with pytest.raises(ArtifactOutboundAuthError, match="not referenced"):
        await resolve_injected_headers(
            db=db_session,
            grant=grant,
            credential_id=_credential_ref(second),
            url="https://google.serper.dev/search",
        )


@pytest.mark.asyncio
async def test_resolve_injected_headers_rejects_tampered_grant(db_session):
    with pytest.raises(ArtifactOutboundAuthError, match="Invalid outbound grant"):
        await resolve_injected_headers(
            db=db_session,
            grant="tampered-token",
            credential_id=str(uuid4()),
            url="https://api.openai.com/v1/chat/completions",
        )
