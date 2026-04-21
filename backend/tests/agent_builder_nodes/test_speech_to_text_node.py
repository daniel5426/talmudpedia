from __future__ import annotations

import io
from types import SimpleNamespace
from uuid import uuid4

import pytest
from starlette.datastructures import UploadFile

from app.agent.executors.speech import SpeechToTextNodeExecutor
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.db.postgres.models.identity import Organization, User
from app.services.model_runtime.interfaces import SpeechToTextResult
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.speech_to_text_service import SpeechToTextService


def _make_upload(filename: str, payload: bytes, content_type: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(payload), filename=filename, size=len(payload), headers={"content-type": content_type})


async def _seed_owner(db_session) -> RuntimeAttachmentOwner:
    suffix = uuid4().hex[:8]
    tenant = Organization(name=f"Organization {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"user-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return RuntimeAttachmentOwner(
        organization_id=tenant.id,
        surface=AgentThreadSurface.internal,
        user_id=user.id,
    )


@pytest.mark.asyncio
async def test_speech_to_text_node_transcribes_audio_attachments_from_workflow_input(db_session, monkeypatch):
    owner = await _seed_owner(db_session)
    attachment_service = RuntimeAttachmentService(db_session)
    uploaded = await attachment_service.upload_files(
        owner=owner,
        files=[_make_upload("memo.mp3", b"audio-bytes", "audio/mpeg")],
    )
    serialized_attachment = attachment_service.serialize_attachment(uploaded[0])

    async def _fake_transcribe(self, audio_content: bytes, **kwargs):
        assert audio_content == b"audio-bytes"
        assert kwargs["attachment_id"] == str(uploaded[0].id)
        return (
            SpeechToTextResult(
                text="Transcript text",
                segments=[{"text": "Transcript text", "confidence": 0.98}],
                language="en-US",
            ),
            SimpleNamespace(
                logical_model=SimpleNamespace(id=uuid4()),
                binding=SimpleNamespace(provider_model_id="chirp_3"),
                resolved_provider="google",
            ),
        )

    monkeypatch.setattr(SpeechToTextService, "transcribe_bytes", _fake_transcribe)

    executor = SpeechToTextNodeExecutor(organization_id=owner.organization_id, db=db_session)
    result = await executor.execute(
        state={
            "workflow_input": {"audio_attachments": [serialized_attachment]},
            "state": {
                "context": {
                    "user_id": str(owner.user_id),
                    "surface": AgentThreadSurface.internal.value,
                }
            },
        },
        config={"source": {"namespace": "workflow_input", "key": "audio_attachments"}},
        context={"node_id": "stt_1", "node_name": "Speech to Text"},
    )

    output = result["stt_output"]

    assert output["text"] == "Transcript text"
    assert output["language"] == "en-US"
    assert output["attachments"] == [str(uploaded[0].id)]
    assert output["provider_metadata"] == {
        "provider": "google",
        "provider_model_id": "chirp_3",
    }
    assert output["segments"] == [
        {
            "text": "Transcript text",
            "attachment_id": str(uploaded[0].id),
            "start_ms": None,
            "end_ms": None,
            "confidence": 0.98,
        }
    ]
