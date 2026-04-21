from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.model_resolver import ModelResolver
from app.services.model_runtime.interfaces import SpeechToTextResult
from app.services.resource_policy_service import ResourcePolicySnapshot


class SpeechToTextService:
    def __init__(self, db: AsyncSession, organization_id: UUID | None):
        self._db = db
        self._organization_id = organization_id

    async def transcribe_bytes(
        self,
        audio_content: bytes,
        *,
        model_id: str | None = None,
        mime_type: str | None = None,
        filename: str | None = None,
        language_hints: list[str] | None = None,
        prompt: str | None = None,
        attachment_id: str | None = None,
        policy_snapshot: ResourcePolicySnapshot | None = None,
    ) -> tuple[SpeechToTextResult, Any]:
        execution = await ModelResolver(self._db, self._organization_id).resolve_speech_to_text_execution(
            model_id=model_id,
            policy_snapshot=policy_snapshot,
        )
        result = await execution.provider_instance.transcribe(
            audio_content,
            mime_type=mime_type,
            filename=filename,
            language_hints=language_hints,
            prompt=prompt,
            attachment_id=attachment_id,
        )
        return result, execution
