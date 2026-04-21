from __future__ import annotations

import logging
from typing import Any

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.graph.contracts import normalize_value_ref, resolve_runtime_value_ref
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.db.postgres.models.runtime_attachments import RuntimeAttachmentKind
from app.services.run_invocation_service import RunInvocationService
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.speech_to_text_service import SpeechToTextService


logger = logging.getLogger(__name__)


class SpeechToTextNodeExecutor(BaseNodeExecutor):
    async def validate_config(self, config: dict[str, Any]) -> ValidationResult:
        source = config.get("source")
        if not isinstance(source, dict):
            return ValidationResult(valid=False, errors=["Speech-to-text node requires a source value_ref"])
        return ValidationResult(valid=True)

    async def execute(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_ref = normalize_value_ref(config.get("source"))
        if not source_ref.get("namespace") or not source_ref.get("key"):
            raise ValueError("Speech-to-text node requires a valid source value_ref")

        resolved = resolve_runtime_value_ref(state=state, value_ref=source_ref)
        attachment_ids = self._normalize_attachment_ids(resolved)
        if not attachment_ids:
            raise ValueError("Speech-to-text source resolved to no attachments")

        attachment_service = RuntimeAttachmentService(self.db)
        owner = self._build_attachment_owner(state=state, context=context)
        attachments = await attachment_service.load_attachments(owner=owner, attachment_ids=attachment_ids)
        await attachment_service.bind_unbound_attachments(owner=owner, attachments=attachments)
        await attachment_service.ensure_processed(attachments=attachments)

        audio_attachments = [attachment for attachment in attachments if attachment.kind == RuntimeAttachmentKind.audio]
        if len(audio_attachments) != len(attachments):
            raise ValueError("Speech-to-text node only accepts audio attachments")

        stt_service = SpeechToTextService(self.db, self.organization_id)
        language_hints = self._normalize_language_hints(config.get("language_hints"))
        prompt = str(config.get("prompt") or "").strip() or None
        model_id = str(config.get("model_id") or "").strip() or None

        from app.agent.execution.emitter import active_emitter

        emitter = active_emitter.get()
        node_id = context.get("node_id", "speech_to_text") if context else "speech_to_text"
        node_name = context.get("node_name", "Speech to Text") if context else "Speech to Text"
        if emitter:
            emitter.emit_node_start(node_id, node_name, "speech_to_text", {"attachments": len(audio_attachments)})

        text_parts: list[str] = []
        segments: list[dict[str, Any]] = []
        languages: list[str] = []
        combined_usage: dict[str, Any] = {}
        resolved_execution = None
        for attachment in audio_attachments:
            payload = attachment_service.read_bytes(attachment)
            result, resolved_execution = await stt_service.transcribe_bytes(
                payload,
                model_id=model_id,
                mime_type=attachment.mime_type,
                filename=attachment.filename,
                language_hints=language_hints,
                prompt=prompt,
                attachment_id=str(attachment.id),
            )
            transcript = str(result.text or "").strip()
            if transcript:
                text_parts.append(transcript)
            for segment in result.segments:
                item = segment.model_dump()
                item["attachment_id"] = str(attachment.id)
                segments.append(item)
            if result.language:
                languages.append(result.language)
            combined_usage = self._merge_usage(combined_usage, dict(result.usage or {}))

        output_payload = {
            "text": "\n\n".join(part for part in text_parts if part).strip(),
            "segments": segments,
            "language": languages[0] if languages else None,
            "attachments": [str(attachment.id) for attachment in audio_attachments],
            "provider_metadata": (
                {
                    "provider": resolved_execution.resolved_provider,
                    "provider_model_id": resolved_execution.binding.provider_model_id,
                }
                if resolved_execution is not None
                else {}
            ),
        }
        invocation_payload = None
        if resolved_execution is not None:
            invocation_payload = RunInvocationService.build_invocation_payload(
                model_id=str(resolved_execution.logical_model.id),
                resolved_provider=resolved_execution.resolved_provider,
                resolved_provider_model_id=resolved_execution.binding.provider_model_id,
                node_id=node_id,
                node_name=node_name,
                node_type="speech_to_text",
                max_context_tokens=None,
                max_context_tokens_source="not_applicable",
                context_input_tokens=None,
                context_source="unknown",
                exact_usage_payload=combined_usage,
                estimated_output_tokens=None,
            )
        if emitter:
            emitter.emit_node_end(
                node_id,
                node_name,
                "speech_to_text",
                {
                    "text_length": len(output_payload["text"]),
                    "usage": invocation_payload["usage"] if invocation_payload else None,
                    "invocation": invocation_payload,
                },
            )
        return {"stt_output": output_payload}

    def _build_attachment_owner(
        self,
        *,
        state: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> RuntimeAttachmentOwner:
        runtime_context = {}
        if isinstance(state.get("state"), dict) and isinstance(state["state"].get("context"), dict):
            runtime_context = dict(state["state"]["context"])
        if context and isinstance(context.get("state_context"), dict):
            runtime_context = {**runtime_context, **dict(context.get("state_context") or {})}

        surface_raw = str(runtime_context.get("surface") or AgentThreadSurface.internal.value).strip()
        try:
            surface = AgentThreadSurface(surface_raw)
        except Exception:
            surface = AgentThreadSurface.internal
        return RuntimeAttachmentOwner(
            organization_id=self.organization_id,
            surface=surface,
            user_id=self._maybe_uuid(runtime_context.get("user_id")),
            app_account_id=self._maybe_uuid(runtime_context.get("published_app_account_id")),
            organization_api_key_id=self._maybe_uuid(runtime_context.get("organization_api_key_id")),
            agent_id=self._maybe_uuid(runtime_context.get("agent_id")),
            published_app_id=self._maybe_uuid(runtime_context.get("published_app_id")),
            external_user_id=str(runtime_context.get("external_user_id") or "").strip() or None,
            external_session_id=str(runtime_context.get("external_session_id") or "").strip() or None,
            thread_id=self._maybe_uuid(runtime_context.get("thread_id")),
        )

    @staticmethod
    def _maybe_uuid(value: Any):
        from uuid import UUID

        try:
            return UUID(str(value)) if value not in (None, "") else None
        except Exception:
            return None

    @staticmethod
    def _normalize_attachment_ids(value: Any) -> list[str]:
        if isinstance(value, dict):
            attachment_id = str(value.get("id") or "").strip()
            return [attachment_id] if attachment_id else []
        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []
        if isinstance(value, list):
            results: list[str] = []
            for item in value:
                results.extend(SpeechToTextNodeExecutor._normalize_attachment_ids(item))
            deduped: list[str] = []
            for item in results:
                if item and item not in deduped:
                    deduped.append(item)
            return deduped
        return []

    @staticmethod
    def _normalize_language_hints(value: Any) -> list[str] | None:
        if isinstance(value, list):
            hints = [str(item).strip() for item in value if str(item).strip()]
            return hints or None
        if isinstance(value, str):
            hints = [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]
            return hints or None
        return None

    @staticmethod
    def _merge_usage(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base or {})
        for key, value in (extra or {}).items():
            if isinstance(value, (int, float)):
                merged[key] = merged.get(key, 0) + value
            elif value not in (None, "", [], {}):
                merged[key] = value
        return merged
