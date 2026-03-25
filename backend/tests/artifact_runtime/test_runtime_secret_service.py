from uuid import uuid4

import pytest

from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.services.artifact_runtime.runtime_secret_service import (
    ArtifactRuntimeSecretError,
    collect_runtime_credential_refs,
    resolve_runtime_credentials,
    rewrite_source_files_for_context_credentials,
)
from types import SimpleNamespace


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid4(), name="Runtime Secret Tenant", slug=f"runtime-secret-{uuid4().hex[:8]}")
    user = User(id=uuid4(), email=f"runtime-secret-{uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid4(),
        tenant_id=tenant.id,
        name="Runtime Secret Org",
        slug=f"runtime-secret-org-{uuid4().hex[:6]}",
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


def test_normalize_credential_reference_supports_token_and_plain_id():
    credential_id = str(uuid4())
    assert collect_runtime_credential_refs(
        language="python",
        source_files=[{"path": "main.py", "content": f'API_KEY = "@{{{credential_id}}}"\n'}],
    ) == [credential_id]


def test_validate_runtime_credential_references_accepts_exact_string_literals():
    first_id = uuid4()
    second_id = uuid4()

    ids = collect_runtime_credential_refs(
        language="python",
        source_files=[
            {
                "path": "main.py",
                "content": (
                    f'API_KEY = "@{{{first_id}}}"\n'
                    f"def execute(inputs, config, context):\n"
                    f'    return {{"token": "@{{{second_id}}}"}}\n'
                ),
            },
        ],
    )

    assert {str(item) for item in ids} == {str(first_id), str(second_id)}


@pytest.mark.parametrize(
    "content",
    [
        'API_KEY = "Bearer @{11111111-1111-1111-1111-111111111111}"\n',
        'API_KEY = f"@{11111111-1111-1111-1111-111111111111}"\n',
        'API_KEY = "@{11111111-1111-1111-1111-111111111111}" "suffix"\n',
        'CONFIG = {"@{11111111-1111-1111-1111-111111111111}": "value"}\n',
        '# @{11111111-1111-1111-1111-111111111111}\n',
        'from artifact_runtime_sdk import resolve_secret\n',
    ],
)
def test_validate_runtime_credential_references_rejects_unsupported_usage(content):
    with pytest.raises(ArtifactRuntimeSecretError, match="supported|artifact_runtime_sdk"):
        collect_runtime_credential_refs(language="python", source_files=[{"path": "main.py", "content": content}])


@pytest.mark.asyncio
async def test_resolve_runtime_secret_values_uses_default_scalar_field(db_session):
    tenant, _user = await _seed_tenant_context(db_session)
    credential = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        display_name="OpenAI Runtime",
        credentials={"api_key": "super-secret-key", "organization": "org_123"},
        is_enabled=True,
        is_default=True,
    )
    db_session.add(credential)
    await db_session.commit()

    revision = SimpleNamespace(manifest_json={"credential_refs": [str(credential.id)]})
    resolved = await resolve_runtime_credentials(
        db=db_session,
        tenant_id=tenant.id,
        revision=revision,
    )

    assert resolved == {str(credential.id): "super-secret-key"}


@pytest.mark.asyncio
async def test_resolve_runtime_secret_values_rejects_missing_or_disabled_or_non_scalar(db_session):
    tenant, _user = await _seed_tenant_context(db_session)
    disabled = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.LLM_PROVIDER,
        provider_key="openai",
        display_name="Disabled Key",
        credentials={"api_key": "disabled-secret"},
        is_enabled=False,
        is_default=False,
    )
    nonscalar = IntegrationCredential(
        tenant_id=tenant.id,
        category=IntegrationCredentialCategory.CUSTOM,
        provider_key="custom",
        display_name="Non Scalar",
        credentials={"endpoint": "https://example.com"},
        is_enabled=True,
        is_default=False,
    )
    db_session.add_all([disabled, nonscalar])
    await db_session.commit()

    with pytest.raises(ArtifactRuntimeSecretError, match="disabled"):
        await resolve_runtime_credentials(
            db=db_session,
            tenant_id=tenant.id,
            revision=SimpleNamespace(manifest_json={"credential_refs": [str(disabled.id)]}),
        )

    with pytest.raises(ArtifactRuntimeSecretError, match="default scalar"):
        await resolve_runtime_credentials(
            db=db_session,
            tenant_id=tenant.id,
            revision=SimpleNamespace(manifest_json={"credential_refs": [str(nonscalar.id)]}),
        )


def test_rewrite_source_files_with_runtime_secrets_rewrites_to_context_credentials_only():
    credential_id = str(uuid4())
    source_files = [{"path": "main.py", "content": f'API_KEY = "@{{{credential_id}}}"\n'}]

    rewritten = rewrite_source_files_for_context_credentials(
        language="python",
        source_files=source_files,
    )

    assert source_files[0]["content"] == f'API_KEY = "@{{{credential_id}}}"\n'
    assert "context['credentials']" in rewritten[0]["content"]
    assert credential_id in rewritten[0]["content"]
