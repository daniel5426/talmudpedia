from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.postgres.models.identity import Tenant
from app.db.postgres.models.registry import (
    ModelCapabilityType,
    ModelProviderBinding,
    ModelProviderType,
    ModelRegistry,
    ModelStatus,
)
from app.services import registry_seeding
from app.services.model_resolver import ModelResolver, ModelResolverError
from app.services.model_runtime import (
    ModelRuntimeAdapterRegistry,
    ResolvedModelRuntimeExecution,
    SpeechToTextResult,
    register_default_model_runtime_adapters,
)
from app.services.model_runtime.adapters import _build_google_stt_runtime


def test_default_runtime_registry_exposes_google_speech_to_text():
    register_default_model_runtime_adapters()

    assert ModelRuntimeAdapterRegistry.supports(
        capability=ModelCapabilityType.SPEECH_TO_TEXT,
        provider=ModelProviderType.GOOGLE,
    )


@pytest.mark.asyncio
async def test_global_seed_includes_default_google_speech_to_text_model(db_session):
    await registry_seeding.seed_global_models(db_session)

    seeded_model = (
        (
            await db_session.execute(
                select(ModelRegistry)
                .where(ModelRegistry.system_key == "google-chirp-3")
                .options(selectinload(ModelRegistry.providers))
            )
        )
        .scalars()
        .one()
    )

    assert seeded_model.capability_type == ModelCapabilityType.SPEECH_TO_TEXT
    assert seeded_model.is_default is True
    assert seeded_model.is_active is True
    assert seeded_model.providers[0].provider == ModelProviderType.GOOGLE
    assert seeded_model.providers[0].provider_model_id == "chirp_3"


@pytest.mark.asyncio
async def test_speech_to_text_default_resolution_returns_typed_execution_receipt(db_session, monkeypatch):
    tenant = Tenant(name=f"Tenant {uuid4().hex[:8]}", slug=f"tenant-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()

    model = ModelRegistry(
        tenant_id=tenant.id,
        name="Default STT",
        capability_type=ModelCapabilityType.SPEECH_TO_TEXT,
        status=ModelStatus.ACTIVE,
        is_active=True,
        is_default=True,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    binding = ModelProviderBinding(
        model_id=model.id,
        tenant_id=tenant.id,
        provider=ModelProviderType.GOOGLE,
        provider_model_id="chirp_3",
        priority=0,
        config={"project_id": "test-project", "location": "us"},
        is_enabled=True,
    )
    db_session.add(binding)
    await db_session.commit()

    class _FakeSpeechRuntime:
        async def transcribe(self, audio_content: bytes, **kwargs):
            return SpeechToTextResult(text=f"len={len(audio_content)}", provider_metadata=kwargs)

    resolver = ModelResolver(db_session, tenant.id)
    original_factories = dict(ModelRuntimeAdapterRegistry._factories)

    async def _fake_factory(**kwargs):
        assert kwargs["binding"].id == binding.id
        assert kwargs["merged_config"]["project_id"] == "test-project"
        return _FakeSpeechRuntime()

    monkeypatch.setattr(
        ModelRuntimeAdapterRegistry,
        "_factories",
        {
            **original_factories,
            (ModelCapabilityType.SPEECH_TO_TEXT, ModelProviderType.GOOGLE): _fake_factory,
        },
    )

    execution = await resolver.resolve_speech_to_text_execution()

    assert isinstance(execution, ResolvedModelRuntimeExecution)
    assert execution.capability_type == ModelCapabilityType.SPEECH_TO_TEXT
    assert execution.logical_model.id == model.id
    assert execution.binding.id == binding.id
    assert execution.binding_scope == "tenant"
    assert execution.merged_config["project_id"] == "test-project"
    assert execution.resolved_provider == "google"
    assert isinstance(execution.provider_instance, _FakeSpeechRuntime)


@pytest.mark.asyncio
async def test_speech_to_text_resolution_rejects_runtime_unsupported_provider(db_session):
    tenant = Tenant(name=f"Tenant {uuid4().hex[:8]}", slug=f"tenant-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()

    model = ModelRegistry(
        tenant_id=tenant.id,
        name="Broken STT",
        capability_type=ModelCapabilityType.SPEECH_TO_TEXT,
        status=ModelStatus.ACTIVE,
        is_active=True,
        metadata_={},
    )
    db_session.add(model)
    await db_session.flush()

    db_session.add(
        ModelProviderBinding(
            model_id=model.id,
            tenant_id=tenant.id,
            provider=ModelProviderType.OPENAI,
            provider_model_id="gpt-4o-mini-transcribe",
            priority=0,
            config={},
            is_enabled=True,
        )
    )
    await db_session.commit()

    with pytest.raises(ModelResolverError, match="not runtime-supported"):
        await ModelResolver(db_session, tenant.id).resolve_speech_to_text_execution(model_id=str(model.id))


@pytest.mark.asyncio
async def test_stt_api_uses_default_registry_resolution(client, db_session, monkeypatch):
    captured: dict[str, object] = {}

    class _FakeSpeechRuntime:
        async def transcribe(self, audio_content: bytes, **kwargs):
            captured["audio_content"] = audio_content
            captured["mime_type"] = kwargs.get("mime_type")
            captured["filename"] = kwargs.get("filename")
            return SpeechToTextResult(text="transcribed from registry")

    async def _fake_resolve(self, model_id=None, policy_override=None, policy_snapshot=None):
        del policy_override, policy_snapshot
        captured["model_id"] = model_id
        return SimpleNamespace(
            provider_instance=_FakeSpeechRuntime(),
            logical_model=SimpleNamespace(id=uuid4()),
            binding=SimpleNamespace(provider_model_id="chirp_3"),
            resolved_provider="google",
        )

    monkeypatch.setattr(ModelResolver, "resolve_speech_to_text_execution", _fake_resolve)

    response = await client.post(
        "/stt/transcribe",
        files={"file": ("memo.mp3", b"audio-bytes", "audio/mpeg")},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "transcribed from registry"}
    assert captured["model_id"] is None
    assert captured["audio_content"] == b"audio-bytes"
    assert captured["mime_type"] == "audio/mpeg"
    assert captured["filename"] == "memo.mp3"


@pytest.mark.asyncio
async def test_google_stt_runtime_accepts_inline_env_credentials_json(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_from_service_account_info(info):
        captured["info"] = info
        return object()

    def _fake_from_service_account_file(path):
        raise AssertionError(f"unexpected file credential path: {path}")

    class _FakeSpeechClient:
        def __init__(self, credentials=None, client_options=None):
            captured["credentials"] = credentials
            captured["client_options"] = client_options

    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS",
        '{"type":"service_account","project_id":"test-project","private_key":"-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n","client_email":"stt@test-project.iam.gserviceaccount.com","token_uri":"https://oauth2.googleapis.com/token"}',
    )
    monkeypatch.setattr(
        "app.services.model_runtime.adapters.service_account.Credentials.from_service_account_info",
        _fake_from_service_account_info,
    )
    monkeypatch.setattr(
        "app.services.model_runtime.adapters.service_account.Credentials.from_service_account_file",
        _fake_from_service_account_file,
    )
    monkeypatch.setattr("app.services.model_runtime.adapters.speech_v2.SpeechClient", _FakeSpeechClient)

    runtime = await _build_google_stt_runtime(
        binding=SimpleNamespace(provider_model_id="chirp_3"),
        model=SimpleNamespace(),
        merged_config={"project_id": "test-project"},
        credentials_payload={},
    )

    assert runtime.project_id == "test-project"
    assert captured["info"] == {
        "type": "service_account",
        "project_id": "test-project",
        "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
        "client_email": "stt@test-project.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    assert captured["client_options"] == {"api_endpoint": "us-speech.googleapis.com"}
