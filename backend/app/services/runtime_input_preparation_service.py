from __future__ import annotations

import base64
from typing import Iterable, Sequence

from app.db.postgres.models.runtime_attachments import RuntimeAttachment, RuntimeAttachmentKind
from app.services.runtime_attachment_service import (
    PreparedAttachmentMessage,
    RuntimeAttachmentOwner,
    RuntimeAttachmentService,
)
from app.services.speech_to_text_service import SpeechToTextService


class RuntimeInputPreparationService:
    def __init__(self, attachment_service: RuntimeAttachmentService, *, stt_service: SpeechToTextService):
        self._attachment_service = attachment_service
        self._stt_service = stt_service

    async def prepare_for_run(
        self,
        *,
        owner: RuntimeAttachmentOwner,
        attachment_ids: Sequence[str] | None,
        input_text: str | None,
        model_ids: Iterable[str] | None = None,
        transcribe_audio: bool = True,
        stt_model_id: str | None = None,
    ) -> PreparedAttachmentMessage:
        normalized_ids = [str(item).strip() for item in (attachment_ids or []) if str(item).strip()]
        attachments: list[RuntimeAttachment] = []
        if normalized_ids:
            attachments = await self._attachment_service.load_attachments(owner=owner, attachment_ids=normalized_ids)
            await self._attachment_service.bind_unbound_attachments(owner=owner, attachments=attachments)
            await self._attachment_service.ensure_processed(attachments=attachments)

        if not attachments:
            display_text = str(input_text or "").strip() or None
            return PreparedAttachmentMessage(content=display_text or None, display_text=display_text, attachments=[])

        if any(attachment.kind == RuntimeAttachmentKind.image for attachment in attachments):
            await self._attachment_service.assert_image_models_supported(model_ids=model_ids or [])

        transcripts: dict[str, str] = {}
        if transcribe_audio:
            for attachment in attachments:
                if attachment.kind != RuntimeAttachmentKind.audio:
                    continue
                payload = self._attachment_service.read_bytes(attachment)
                result, _execution = await self._stt_service.transcribe_bytes(
                    payload,
                    model_id=stt_model_id,
                    mime_type=attachment.mime_type,
                    filename=attachment.filename,
                    attachment_id=str(attachment.id),
                )
                transcripts[str(attachment.id)] = result.text.strip()

        content = self._build_user_message_content(
            input_text=input_text,
            attachments=attachments,
            transcripts=transcripts,
        )
        display_text = self._build_display_text(
            input_text=input_text,
            attachments=attachments,
            transcripts=transcripts,
        )
        return PreparedAttachmentMessage(content=content, display_text=display_text, attachments=attachments)

    @staticmethod
    def build_workflow_input_payload(
        *,
        input_text: str | None = None,
        attachments: Sequence[dict],
    ) -> dict[str, object]:
        payload = [dict(item) for item in attachments if isinstance(item, dict)]
        files_only = [item for item in payload if str(item.get("kind") or "").strip().lower() == "document"]
        audio_only = [item for item in payload if str(item.get("kind") or "").strip().lower() == "audio"]
        images_only = [item for item in payload if str(item.get("kind") or "").strip().lower() == "image"]
        workflow_input: dict[str, object] = {}
        if input_text is not None:
            workflow_input["text"] = str(input_text or "")
            workflow_input["input_as_text"] = str(input_text or "")
        if payload:
            workflow_input["attachments"] = payload
            workflow_input["files"] = files_only
            workflow_input["audio"] = audio_only
            workflow_input["images"] = images_only
            workflow_input["audio_attachments"] = audio_only
        if audio_only:
            workflow_input["primary_audio_attachment"] = dict(audio_only[0])
        return workflow_input

    def _build_user_message_content(
        self,
        *,
        input_text: str | None,
        attachments: Sequence[RuntimeAttachment],
        transcripts: dict[str, str],
    ) -> str | list[dict[str, object]] | None:
        text_sections: list[str] = []
        normalized_input = str(input_text or "").strip()
        if normalized_input:
            text_sections.append(normalized_input)

        image_parts: list[dict[str, object]] = []
        for attachment in attachments:
            if attachment.kind == RuntimeAttachmentKind.audio:
                transcript = transcripts.get(str(attachment.id), "").strip()
                if transcript:
                    text_sections.append(f"Audio transcript ({attachment.filename}):\n{transcript}")
            elif attachment.kind == RuntimeAttachmentKind.document:
                extracted = str(attachment.extracted_text or "").strip()
                if extracted:
                    text_sections.append(f"Attached document ({attachment.filename}):\n{extracted}")
            elif attachment.kind == RuntimeAttachmentKind.image:
                payload = self._attachment_service.read_bytes(attachment)
                data_uri = f"data:{attachment.mime_type};base64,{base64.b64encode(payload).decode('ascii')}"
                image_parts.append({"type": "image_url", "image_url": {"url": data_uri}})

        text_content = "\n\n".join(section for section in text_sections if section).strip()
        if image_parts:
            parts: list[dict[str, object]] = []
            if text_content:
                parts.append({"type": "text", "text": text_content})
            parts.extend(image_parts)
            return parts
        return text_content or None

    def _build_display_text(
        self,
        *,
        input_text: str | None,
        attachments: Sequence[RuntimeAttachment],
        transcripts: dict[str, str],
    ) -> str | None:
        normalized_input = str(input_text or "").strip()
        attachment_names = ", ".join(attachment.filename for attachment in attachments if attachment.filename)
        audio_only = [attachment for attachment in attachments if attachment.kind == RuntimeAttachmentKind.audio]
        non_audio = [attachment for attachment in attachments if attachment.kind != RuntimeAttachmentKind.audio]
        if normalized_input and attachment_names:
            return f"{normalized_input}\n\nAttachments: {attachment_names}"
        if normalized_input:
            return normalized_input
        if len(audio_only) == 1 and not non_audio:
            transcript = transcripts.get(str(audio_only[0].id), "").strip()
            if transcript:
                return transcript
        if attachment_names:
            return f"Uploaded attachments: {attachment_names}"
        return None
