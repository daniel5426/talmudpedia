from __future__ import annotations

import io
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.datastructures import UploadFile

from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import (
    ModelCapabilityType,
    ModelProviderBinding,
    ModelProviderType,
    ModelRegistry,
)
from app.db.postgres.models.runtime_attachments import RuntimeAttachmentStatus
from app.services.model_runtime.interfaces import SpeechToTextResult
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.runtime_input_preparation_service import RuntimeInputPreparationService
from app.services.runtime_attachment_storage import RuntimeAttachmentStorage


def _make_upload(filename: str, payload: bytes, content_type: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(payload), filename=filename, size=len(payload), headers={"content-type": content_type})


async def _seed_owner(db_session) -> RuntimeAttachmentOwner:
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"user-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return RuntimeAttachmentOwner(
        tenant_id=tenant.id,
        surface=AgentThreadSurface.internal,
        user_id=user.id,
    )


async def _seed_model(
    db_session,
    *,
    owner: RuntimeAttachmentOwner,
    capability_type: ModelCapabilityType = ModelCapabilityType.CHAT,
    metadata: dict | None = None,
    provider_model_id: str | None = None,
) -> ModelRegistry:
    model = ModelRegistry(
        tenant_id=owner.tenant_id,
        name=f"Model {uuid4().hex[:6]}",
        capability_type=capability_type,
        metadata_=dict(metadata or {}),
        is_active=True,
    )
    db_session.add(model)
    await db_session.flush()
    if provider_model_id is not None:
        db_session.add(
            ModelProviderBinding(
                model_id=model.id,
                tenant_id=owner.tenant_id,
                provider=ModelProviderType.OPENAI,
                provider_model_id=provider_model_id,
                is_enabled=True,
                config={},
            )
        )
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content_type", "payload", "expected_snippet"),
    [
        ("brief.txt", "text/plain", b"Quarterly results are strong.", "Quarterly results are strong."),
        ("notes.md", "text/markdown", b"# Header\n\nImportant note", "# Header\n\nImportant note"),
        ("table.csv", "text/csv", b"name,amount\nalice,5\nbob,7\n", "name, amount\nalice, 5\nbob, 7"),
        ("data.json", "application/json", b'{"a":1,"b":{"c":2}}', '"b": {\n    "c": 2\n  }'),
        ("page.html", "text/html", b"<h1>Title</h1><p>Hello</p>", "<h1>Title</h1><p>Hello</p>"),
    ],
)
async def test_document_attachments_are_processed_and_injected_into_user_message(
    db_session,
    tmp_path,
    filename,
    content_type,
    payload,
    expected_snippet,
):
    owner = await _seed_owner(db_session)
    service = RuntimeAttachmentService(db_session, storage=RuntimeAttachmentStorage(str(tmp_path)))

    uploaded = await service.upload_files(
        owner=owner,
        files=[_make_upload(filename, payload, content_type)],
    )
    prepared = await service.prepare_for_run(
        owner=owner,
        attachment_ids=[str(uploaded[0].id)],
        input_text="Summarize this",
        model_ids=[],
    )

    await db_session.refresh(uploaded[0])
    assert uploaded[0].status == RuntimeAttachmentStatus.processed
    assert uploaded[0].metadata_["processor"] == "document_text_extract"
    assert isinstance(prepared.content, str)
    assert "Summarize this" in prepared.content
    assert expected_snippet in prepared.content


@pytest.mark.asyncio
async def test_pdf_attachment_uses_document_extractor_path(db_session, tmp_path, monkeypatch):
    owner = await _seed_owner(db_session)
    service = RuntimeAttachmentService(db_session, storage=RuntimeAttachmentStorage(str(tmp_path)))
    monkeypatch.setattr(
        service,
        "_extract_document_text",
        lambda **kwargs: "Extracted PDF contents",
    )

    uploaded = await service.upload_files(
        owner=owner,
        files=[_make_upload("report.pdf", b"%PDF-1.4 fake", "application/pdf")],
    )
    prepared = await service.prepare_for_run(
        owner=owner,
        attachment_ids=[str(uploaded[0].id)],
        input_text=None,
        model_ids=[],
    )

    await db_session.refresh(uploaded[0])
    assert uploaded[0].status == RuntimeAttachmentStatus.processed
    assert uploaded[0].extracted_text == "Extracted PDF contents"
    assert prepared.content == "Attached document (report.pdf):\nExtracted PDF contents"


@pytest.mark.asyncio
async def test_runtime_attachment_service_keeps_audio_storage_prep_transcription_free(db_session, tmp_path):
    owner = await _seed_owner(db_session)
    service = RuntimeAttachmentService(db_session, storage=RuntimeAttachmentStorage(str(tmp_path)))

    uploaded = await service.upload_files(
        owner=owner,
        files=[_make_upload("memo.mp3", b"audio-bytes", "audio/mpeg")],
    )
    prepared = await service.prepare_for_run(
        owner=owner,
        attachment_ids=[str(uploaded[0].id)],
        input_text="Use the memo",
        model_ids=[],
    )

    await db_session.refresh(uploaded[0])
    assert uploaded[0].status == RuntimeAttachmentStatus.processed
    assert uploaded[0].metadata_ == {}
    assert uploaded[0].extracted_text is None
    assert prepared.content == "Use the memo"
    assert prepared.display_text == "Use the memo\n\nAttachments: memo.mp3"


@pytest.mark.asyncio
async def test_runtime_input_preparation_transcribes_audio_through_shared_stt_runtime(db_session, tmp_path):
    owner = await _seed_owner(db_session)
    attachment_service = RuntimeAttachmentService(db_session, storage=RuntimeAttachmentStorage(str(tmp_path)))

    class _FakeSpeechToTextService:
        async def transcribe_bytes(self, audio_content: bytes, **kwargs):
            assert audio_content == b"audio-bytes"
            assert kwargs["mime_type"] == "audio/mpeg"
            assert kwargs["filename"] == "memo.mp3"
            return SpeechToTextResult(text="Transcript text"), {"provider": "fake"}

    input_preparation_service = RuntimeInputPreparationService(
        attachment_service,
        stt_service=_FakeSpeechToTextService(),
    )

    uploaded = await attachment_service.upload_files(
        owner=owner,
        files=[_make_upload("memo.mp3", b"audio-bytes", "audio/mpeg")],
    )
    prepared = await input_preparation_service.prepare_for_run(
        owner=owner,
        attachment_ids=[str(uploaded[0].id)],
        input_text="Use the memo",
        model_ids=[],
    )

    await db_session.refresh(uploaded[0])
    assert uploaded[0].status == RuntimeAttachmentStatus.processed
    assert uploaded[0].extracted_text is None
    assert prepared.content == "Use the memo\n\nAudio transcript (memo.mp3):\nTranscript text"
    assert prepared.display_text == "Use the memo\n\nAttachments: memo.mp3"


@pytest.mark.asyncio
async def test_image_attachments_require_vision_capable_model(db_session, tmp_path):
    owner = await _seed_owner(db_session)
    non_vision_model = await _seed_model(db_session, owner=owner, capability_type=ModelCapabilityType.CHAT)
    service = RuntimeAttachmentService(db_session, storage=RuntimeAttachmentStorage(str(tmp_path)))

    uploaded = await service.upload_files(
        owner=owner,
        files=[_make_upload("diagram.png", b"\x89PNG\r\n\x1a\n", "image/png")],
    )

    with pytest.raises(HTTPException) as exc:
        await service.prepare_for_run(
            owner=owner,
            attachment_ids=[str(uploaded[0].id)],
            input_text="Describe the image",
            model_ids=[str(non_vision_model.id)],
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Image attachments require a vision-capable model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capability_type", "metadata", "provider_model_id"),
    [
        (ModelCapabilityType.VISION, {}, None),
        (ModelCapabilityType.CHAT, {"vision": True}, None),
    ],
)
async def test_image_attachments_accept_current_vision_signals(
    db_session,
    tmp_path,
    capability_type,
    metadata,
    provider_model_id,
):
    owner = await _seed_owner(db_session)
    model = await _seed_model(
        db_session,
        owner=owner,
        capability_type=capability_type,
        metadata=metadata,
        provider_model_id=provider_model_id,
    )
    service = RuntimeAttachmentService(db_session, storage=RuntimeAttachmentStorage(str(tmp_path)))

    uploaded = await service.upload_files(
        owner=owner,
        files=[_make_upload("diagram.png", b"\x89PNG\r\n\x1a\n", "image/png")],
    )
    prepared = await service.prepare_for_run(
        owner=owner,
        attachment_ids=[str(uploaded[0].id)],
        input_text="Describe the image",
        model_ids=[str(model.id)],
    )

    await db_session.refresh(uploaded[0])
    assert uploaded[0].status == RuntimeAttachmentStatus.processed
    assert isinstance(prepared.content, list)
    assert prepared.content[0] == {"type": "text", "text": "Describe the image"}
    assert prepared.content[1]["type"] == "image_url"
    assert prepared.content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_image_attachments_ignore_provider_model_name_heuristics(db_session, tmp_path):
    owner = await _seed_owner(db_session)
    model = await _seed_model(
        db_session,
        owner=owner,
        capability_type=ModelCapabilityType.CHAT,
        metadata={},
        provider_model_id="gpt-5-mini-2025-08-07",
    )
    service = RuntimeAttachmentService(db_session, storage=RuntimeAttachmentStorage(str(tmp_path)))

    uploaded = await service.upload_files(
        owner=owner,
        files=[_make_upload("diagram.png", b"\x89PNG\r\n\x1a\n", "image/png")],
    )

    with pytest.raises(HTTPException) as exc:
        await service.prepare_for_run(
            owner=owner,
            attachment_ids=[str(uploaded[0].id)],
            input_text="Describe the image",
            model_ids=[str(model.id)],
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Image attachments require a vision-capable model"


@pytest.mark.asyncio
async def test_attachment_processing_state_is_persisted(db_session, tmp_path):
    owner = await _seed_owner(db_session)
    service = RuntimeAttachmentService(db_session, storage=RuntimeAttachmentStorage(str(tmp_path)))

    uploaded = await service.upload_files(
        owner=owner,
        files=[_make_upload("brief.txt", b"hello world", "text/plain")],
    )
    await service.prepare_for_run(
        owner=owner,
        attachment_ids=[str(uploaded[0].id)],
        input_text=None,
        model_ids=[],
    )

    stored = await db_session.scalar(select(type(uploaded[0])).where(type(uploaded[0]).id == uploaded[0].id))
    assert stored is not None
    assert stored.status == RuntimeAttachmentStatus.processed
    assert stored.extracted_text == "hello world"
