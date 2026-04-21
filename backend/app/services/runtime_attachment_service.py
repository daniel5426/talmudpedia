from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface
from app.db.postgres.models.registry import ModelRegistry, ModelCapabilityType
from app.db.postgres.models.runtime_attachments import (
    AgentThreadTurnAttachment,
    RuntimeAttachment,
    RuntimeAttachmentKind,
    RuntimeAttachmentStatus,
)
from app.services.runtime_attachment_storage import RuntimeAttachmentStorage, RuntimeAttachmentStorageError
from app.services.thread_service import ThreadService


MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_DOCUMENT_TEXT_CHARS = 20000

IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}
DOCUMENT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
    "text/csv",
    "application/json",
    "text/html",
}
DOCUMENT_EXTENSION_MIME_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".json": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
}
AUDIO_MIME_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
}
@dataclass
class RuntimeAttachmentOwner:
    organization_id: UUID
    surface: AgentThreadSurface
    project_id: UUID | None = None
    user_id: UUID | None = None
    app_account_id: UUID | None = None
    organization_api_key_id: UUID | None = None
    agent_id: UUID | None = None
    published_app_id: UUID | None = None
    external_user_id: str | None = None
    external_session_id: str | None = None
    thread_id: UUID | None = None


@dataclass
class PreparedAttachmentMessage:
    content: str | list[dict[str, Any]] | None
    display_text: str | None
    attachments: list[RuntimeAttachment]


class RuntimeAttachmentService:
    def __init__(self, db: AsyncSession, *, storage: RuntimeAttachmentStorage | None = None):
        self.db = db
        self.storage = storage or RuntimeAttachmentStorage()

    async def upload_files(
        self,
        *,
        owner: RuntimeAttachmentOwner,
        files: Sequence[UploadFile],
    ) -> list[RuntimeAttachment]:
        uploaded: list[RuntimeAttachment] = []
        for file in files:
            payload = await file.read()
            if not payload:
                raise HTTPException(status_code=400, detail=f"Uploaded file '{file.filename or 'attachment'}' is empty")
            if len(payload) > MAX_ATTACHMENT_BYTES:
                raise HTTPException(status_code=400, detail=f"Uploaded file '{file.filename or 'attachment'}' exceeds the size limit")

            filename = str(file.filename or "attachment").strip() or "attachment"
            mime_type = self._normalize_mime_type(filename=filename, content_type=file.content_type)
            kind = self._classify_kind(filename=filename, mime_type=mime_type)
            digest = hashlib.sha256(payload).hexdigest()
            attachment = RuntimeAttachment(
                organization_id=owner.organization_id,
                project_id=owner.project_id,
                thread_id=owner.thread_id,
                user_id=owner.user_id,
                app_account_id=owner.app_account_id,
                organization_api_key_id=owner.organization_api_key_id,
                agent_id=owner.agent_id,
                published_app_id=owner.published_app_id,
                external_user_id=owner.external_user_id,
                external_session_id=owner.external_session_id,
                surface=owner.surface,
                kind=kind,
                mime_type=mime_type,
                filename=filename,
                byte_size=len(payload),
                storage_key="pending",
                sha256=digest,
                status=RuntimeAttachmentStatus.processed if kind == RuntimeAttachmentKind.image else RuntimeAttachmentStatus.uploaded,
                metadata_={},
            )
            self.db.add(attachment)
            await self.db.flush()
            attachment.storage_key = self.storage.write_bytes(
                attachment_id=str(attachment.id),
                filename=filename,
                payload=payload,
            )
            uploaded.append(attachment)
        await self.db.flush()
        return uploaded

    async def get_accessible_thread(
        self,
        *,
        owner: RuntimeAttachmentOwner,
        thread_id: UUID,
    ) -> AgentThread | None:
        return await ThreadService(self.db).get_thread_with_turns(
            organization_id=owner.organization_id,
            project_id=owner.project_id,
            thread_id=thread_id,
            user_id=owner.user_id,
            app_account_id=owner.app_account_id,
            published_app_id=owner.published_app_id,
            agent_id=owner.agent_id,
            external_user_id=owner.external_user_id,
            external_session_id=owner.external_session_id,
        )

    async def prepare_for_run(
        self,
        *,
        owner: RuntimeAttachmentOwner,
        attachment_ids: Sequence[str] | None,
        input_text: str | None,
        model_ids: Iterable[str] | None = None,
    ) -> PreparedAttachmentMessage:
        normalized_ids = [str(item).strip() for item in (attachment_ids or []) if str(item).strip()]
        attachments: list[RuntimeAttachment] = []
        if normalized_ids:
            attachments = await self.load_attachments(owner=owner, attachment_ids=normalized_ids)
            await self.bind_unbound_attachments(owner=owner, attachments=attachments)
            await self.ensure_processed(attachments=attachments)

        if not attachments:
            display_text = str(input_text or "").strip() or None
            content = display_text or None
            return PreparedAttachmentMessage(content=content, display_text=display_text, attachments=[])

        if any(attachment.kind == RuntimeAttachmentKind.image for attachment in attachments):
            await self.assert_image_models_supported(model_ids=model_ids or [])

        content = self._build_user_message_content(input_text=input_text, attachments=attachments)
        display_text = self._build_display_text(input_text=input_text, attachments=attachments)
        return PreparedAttachmentMessage(content=content, display_text=display_text, attachments=attachments)

    async def link_attachments_to_turn(
        self,
        *,
        turn_id: UUID,
        attachments: Sequence[RuntimeAttachment],
    ) -> None:
        existing_result = await self.db.execute(
            select(AgentThreadTurnAttachment.attachment_id).where(AgentThreadTurnAttachment.turn_id == turn_id)
        )
        existing_ids = {str(value) for value in existing_result.scalars().all()}
        for attachment in attachments:
            if str(attachment.id) in existing_ids:
                continue
            self.db.add(
                AgentThreadTurnAttachment(
                    turn_id=turn_id,
                    attachment_id=attachment.id,
                )
            )
        await self.db.flush()

    @staticmethod
    def serialize_attachment(attachment: RuntimeAttachment) -> dict[str, Any]:
        loaded = sa_inspect(attachment).dict
        created_at = loaded.get("created_at")
        updated_at = loaded.get("updated_at")
        return {
            "id": str(attachment.id),
            "thread_id": str(attachment.thread_id) if attachment.thread_id else None,
            "kind": attachment.kind.value if hasattr(attachment.kind, "value") else str(attachment.kind),
            "filename": attachment.filename,
            "mime_type": attachment.mime_type,
            "byte_size": int(attachment.byte_size or 0),
            "status": attachment.status.value if hasattr(attachment.status, "value") else str(attachment.status),
            "processing_error": attachment.processing_error,
            "metadata": dict(loaded.get("metadata_") or {}),
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
            "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
        }

    def _normalize_mime_type(self, *, filename: str, content_type: str | None) -> str:
        raw_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
        if raw_content_type:
            return raw_content_type
        guessed, _ = mimetypes.guess_type(filename)
        return str(guessed or "").strip().lower() or "application/octet-stream"

    def _classify_kind(self, *, filename: str, mime_type: str) -> RuntimeAttachmentKind:
        normalized_mime = str(mime_type or "").strip().lower()
        suffix = Path(filename).suffix.lower()
        if normalized_mime in IMAGE_MIME_TYPES:
            return RuntimeAttachmentKind.image
        if normalized_mime in AUDIO_MIME_TYPES:
            return RuntimeAttachmentKind.audio
        if normalized_mime in DOCUMENT_MIME_TYPES:
            return RuntimeAttachmentKind.document
        fallback_document_mime = DOCUMENT_EXTENSION_MIME_TYPES.get(suffix)
        if fallback_document_mime:
            return RuntimeAttachmentKind.document
        raise HTTPException(status_code=400, detail=f"Unsupported attachment type for '{filename}'")

    async def load_attachments(
        self,
        *,
        owner: RuntimeAttachmentOwner,
        attachment_ids: Sequence[str],
    ) -> list[RuntimeAttachment]:
        parsed_ids: list[UUID] = []
        for raw in attachment_ids:
            try:
                parsed_ids.append(UUID(str(raw)))
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid attachment id '{raw}'") from exc
        result = await self.db.execute(
            select(RuntimeAttachment)
            .where(
                RuntimeAttachment.organization_id == owner.organization_id,
                RuntimeAttachment.project_id == owner.project_id,
                RuntimeAttachment.id.in_(parsed_ids),
            )
            .options(selectinload(RuntimeAttachment.turn_links))
        )
        attachments = list(result.scalars().all())
        if len(attachments) != len(parsed_ids):
            raise HTTPException(status_code=404, detail="One or more attachments were not found")
        for attachment in attachments:
            if not self._owner_matches(owner=owner, attachment=attachment):
                raise HTTPException(status_code=403, detail="Attachment access denied")
        return attachments

    def _owner_matches(self, *, owner: RuntimeAttachmentOwner, attachment: RuntimeAttachment) -> bool:
        if attachment.surface != owner.surface:
            return False
        if attachment.project_id != owner.project_id:
            return False
        if owner.agent_id and attachment.agent_id and attachment.agent_id != owner.agent_id:
            return False
        if owner.published_app_id and attachment.published_app_id and attachment.published_app_id != owner.published_app_id:
            return False
        if owner.user_id and attachment.user_id and attachment.user_id != owner.user_id:
            return False
        if owner.app_account_id and attachment.app_account_id and attachment.app_account_id != owner.app_account_id:
            return False
        if owner.organization_api_key_id and attachment.organization_api_key_id and attachment.organization_api_key_id != owner.organization_api_key_id:
            return False
        if owner.external_user_id and attachment.external_user_id and attachment.external_user_id != owner.external_user_id:
            return False
        if owner.external_session_id is not None and attachment.external_session_id is not None and attachment.external_session_id != owner.external_session_id:
            return False
        if attachment.thread_id and owner.thread_id and attachment.thread_id != owner.thread_id:
            return False
        return True

    async def bind_unbound_attachments(
        self,
        *,
        owner: RuntimeAttachmentOwner,
        attachments: Sequence[RuntimeAttachment],
    ) -> None:
        for attachment in attachments:
            if attachment.thread_id is None and owner.thread_id is not None:
                attachment.thread_id = owner.thread_id
            if attachment.project_id is None and owner.project_id is not None:
                attachment.project_id = owner.project_id
            if attachment.agent_id is None and owner.agent_id is not None:
                attachment.agent_id = owner.agent_id
            if attachment.published_app_id is None and owner.published_app_id is not None:
                attachment.published_app_id = owner.published_app_id
            if attachment.user_id is None and owner.user_id is not None:
                attachment.user_id = owner.user_id
            if attachment.app_account_id is None and owner.app_account_id is not None:
                attachment.app_account_id = owner.app_account_id
            if attachment.organization_api_key_id is None and owner.organization_api_key_id is not None:
                attachment.organization_api_key_id = owner.organization_api_key_id
            if attachment.external_user_id is None and owner.external_user_id is not None:
                attachment.external_user_id = owner.external_user_id
            if attachment.external_session_id is None and owner.external_session_id is not None:
                attachment.external_session_id = owner.external_session_id
        await self.db.flush()

    async def ensure_processed(self, *, attachments: Sequence[RuntimeAttachment]) -> None:
        for attachment in attachments:
            if attachment.status == RuntimeAttachmentStatus.failed:
                raise HTTPException(status_code=400, detail=f"Attachment '{attachment.filename}' is unavailable: {attachment.processing_error or 'processing failed'}")
            if attachment.kind == RuntimeAttachmentKind.image:
                if attachment.status != RuntimeAttachmentStatus.processed:
                    attachment.status = RuntimeAttachmentStatus.processed
                continue
            if attachment.kind == RuntimeAttachmentKind.audio:
                if attachment.status != RuntimeAttachmentStatus.processed:
                    attachment.status = RuntimeAttachmentStatus.processed
                continue

            payload = self.read_bytes(attachment)
            try:
                if attachment.kind == RuntimeAttachmentKind.document:
                    if not str(attachment.extracted_text or "").strip():
                        attachment.extracted_text = self._extract_document_text(
                            payload=payload,
                            mime_type=attachment.mime_type,
                            filename=attachment.filename,
                        )
                        attachment.metadata_ = {
                            **dict(attachment.metadata_ or {}),
                            "processor": "document_text_extract",
                        }
                    if not str(attachment.extracted_text or "").strip():
                        raise ValueError("Document extraction returned no text")
                attachment.processing_error = None
                attachment.status = RuntimeAttachmentStatus.processed
            except Exception as exc:
                attachment.status = RuntimeAttachmentStatus.failed
                attachment.processing_error = str(exc)
                await self.db.flush()
                raise HTTPException(status_code=400, detail=f"Failed to process attachment '{attachment.filename}': {exc}") from exc
        await self.db.flush()

    def read_bytes(self, attachment: RuntimeAttachment) -> bytes:
        try:
            return self.storage.read_bytes(storage_key=attachment.storage_key)
        except RuntimeAttachmentStorageError as exc:
            raise HTTPException(status_code=500, detail=f"Attachment payload missing for '{attachment.filename}'") from exc

    def _extract_document_text(self, *, payload: bytes, mime_type: str, filename: str) -> str:
        normalized_mime = str(mime_type or "").strip().lower()
        if normalized_mime == "application/pdf" or Path(filename).suffix.lower() == ".pdf":
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(payload))
            pages = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text.strip())
            return "\n\n".join(pages)[:MAX_DOCUMENT_TEXT_CHARS].strip()

        decoded = payload.decode("utf-8", errors="replace")
        if normalized_mime == "application/json":
            try:
                parsed = json.loads(decoded)
            except Exception:
                return decoded[:MAX_DOCUMENT_TEXT_CHARS].strip()
            return json.dumps(parsed, ensure_ascii=False, indent=2)[:MAX_DOCUMENT_TEXT_CHARS].strip()

        if normalized_mime == "text/csv":
            reader = csv.reader(io.StringIO(decoded))
            rows = []
            for row in reader:
                rows.append(", ".join(cell.strip() for cell in row if str(cell).strip()))
            return "\n".join(item for item in rows if item)[:MAX_DOCUMENT_TEXT_CHARS].strip()

        return decoded[:MAX_DOCUMENT_TEXT_CHARS].strip()

    async def assert_image_models_supported(self, *, model_ids: Iterable[str]) -> None:
        normalized = [str(item).strip() for item in model_ids if str(item).strip()]
        if not normalized:
            raise HTTPException(status_code=400, detail="Image attachments require a vision-capable model")
        for model_id in normalized:
            if await self._model_supports_vision(model_id):
                return
        raise HTTPException(status_code=400, detail="Image attachments require a vision-capable model")

    async def _model_supports_vision(self, model_id: str) -> bool:
        try:
            parsed_model_id = UUID(model_id)
        except Exception:
            return False
        result = await self.db.execute(
            select(ModelRegistry)
            .where(ModelRegistry.id == parsed_model_id)
            .options(selectinload(ModelRegistry.providers))
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return False
        if model.capability_type == ModelCapabilityType.VISION:
            return True
        metadata = dict(model.metadata_ or {})
        if bool(metadata.get("supports_vision")) or bool(metadata.get("vision")):
            return True
        return False

    def _build_user_message_content(
        self,
        *,
        input_text: str | None,
        attachments: Sequence[RuntimeAttachment],
    ) -> str | list[dict[str, Any]] | None:
        text_sections: list[str] = []
        normalized_input = str(input_text or "").strip()
        if normalized_input:
            text_sections.append(normalized_input)

        image_parts: list[dict[str, Any]] = []
        for attachment in attachments:
            if attachment.kind == RuntimeAttachmentKind.audio:
                transcript = str(attachment.extracted_text or "").strip()
                if transcript:
                    text_sections.append(f"Audio transcript ({attachment.filename}):\n{transcript}")
            elif attachment.kind == RuntimeAttachmentKind.document:
                extracted = str(attachment.extracted_text or "").strip()
                if extracted:
                    text_sections.append(f"Attached document ({attachment.filename}):\n{extracted}")
            elif attachment.kind == RuntimeAttachmentKind.image:
                payload = self.read_bytes(attachment)
                data_uri = f"data:{attachment.mime_type};base64,{base64.b64encode(payload).decode('ascii')}"
                image_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    }
                )

        text_content = "\n\n".join(section for section in text_sections if section).strip()
        if image_parts:
            parts: list[dict[str, Any]] = []
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
            transcript = str(audio_only[0].extracted_text or "").strip()
            if transcript:
                return transcript
        if attachment_names:
            return f"Uploaded attachments: {attachment_names}"
        return None
