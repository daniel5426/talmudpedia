from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech
from google.oauth2 import service_account

from app.agent.components.llm.langchain_provider import LangChainProviderAdapter
from app.db.postgres.models.registry import ModelCapabilityType, ModelProviderBinding, ModelProviderType, ModelRegistry
from app.rag.providers.embedding.gemini import GeminiEmbeddingProvider
from app.rag.providers.embedding.huggingface import HuggingFaceEmbeddingProvider
from app.rag.providers.embedding.openai import OpenAIEmbeddingProvider
from app.services.model_runtime.interfaces import SpeechToTextResult, SpeechToTextRuntime
from app.services.model_runtime.registry import ModelRuntimeAdapterRegistry


class GoogleSpeechToTextRuntime(SpeechToTextRuntime):
    def __init__(
        self,
        *,
        project_id: str,
        model: str,
        location: str = "us",
        credentials_info: dict[str, Any] | None = None,
        credentials_path: str | None = None,
        language_codes: list[str] | None = None,
    ) -> None:
        self.project_id = project_id
        self.model = model
        self.location = location
        self.language_codes = list(language_codes or ["en-US", "he-IL"])
        client_options = {"api_endpoint": f"{self.location}-speech.googleapis.com"}
        credentials = None
        if isinstance(credentials_info, dict) and credentials_info:
            credentials = service_account.Credentials.from_service_account_info(credentials_info)
        elif isinstance(credentials_path, str) and credentials_path.strip():
            credentials = service_account.Credentials.from_service_account_file(credentials_path.strip())
        self.client = speech_v2.SpeechClient(credentials=credentials, client_options=client_options)

    async def transcribe(
        self,
        audio_content: bytes,
        *,
        mime_type: str | None = None,
        filename: str | None = None,
        language_hints: list[str] | None = None,
        prompt: str | None = None,
        attachment_id: str | None = None,
    ) -> SpeechToTextResult:
        del mime_type, filename, prompt
        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=list(language_hints or self.language_codes),
            model=self.model,
        )
        request = cloud_speech.RecognizeRequest(
            recognizer=f"projects/{self.project_id}/locations/{self.location}/recognizers/_",
            config=config,
            content=audio_content,
        )
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.client.recognize, request)

        text_parts: list[str] = []
        segments: list[dict[str, Any]] = []
        language: str | None = None
        for result in response.results:
            if getattr(result, "language_code", None):
                language = str(result.language_code)
            if not result.alternatives:
                continue
            alt = result.alternatives[0]
            transcript = str(getattr(alt, "transcript", "") or "").strip()
            if not transcript:
                continue
            text_parts.append(transcript)
            segments.append(
                {
                    "text": transcript,
                    "attachment_id": attachment_id,
                    "confidence": getattr(alt, "confidence", None),
                }
            )

        joined = " ".join(part for part in text_parts if part).strip()
        return SpeechToTextResult(
            text=joined,
            segments=segments,
            language=language,
            attachments=[attachment_id] if attachment_id else [],
            provider_metadata={
                "provider": "google",
                "provider_model_id": self.model,
                "location": self.location,
            },
            usage={"audio_input_tokens": len(audio_content)},
        )


async def _build_chat_langchain_runtime(
    *,
    binding: ModelProviderBinding,
    model: ModelRegistry,
    merged_config: dict[str, Any],
    credentials_payload: dict[str, Any],
) -> Any:
    del model
    api_key = credentials_payload.get("api_key")
    if not api_key and binding.provider != ModelProviderType.LOCAL:
        raise ValueError(f"Missing API Key for provider {binding.provider}")
    runtime_config = dict(merged_config)
    runtime_config.pop("api_key", None)
    return LangChainProviderAdapter(
        provider=binding.provider,
        model=binding.provider_model_id,
        api_key=api_key,
        **runtime_config,
    )


async def _build_embedding_runtime(
    *,
    binding: ModelProviderBinding,
    model: ModelRegistry,
    merged_config: dict[str, Any],
    credentials_payload: dict[str, Any],
) -> Any:
    api_key = credentials_payload.get("api_key")
    metadata = dict(getattr(model, "metadata_", {}) or {})
    dimension = metadata.get("dimension")
    if binding.provider == ModelProviderType.OPENAI:
        return OpenAIEmbeddingProvider(
            api_key=api_key,
            model=binding.provider_model_id,
            dimensions=dimension,
        )
    if binding.provider in (ModelProviderType.GOOGLE, ModelProviderType.GEMINI):
        task_type = merged_config.get("task_type") or credentials_payload.get("task_type")
        return GeminiEmbeddingProvider(
            api_key=api_key,
            model=binding.provider_model_id,
            task_type=task_type or "QUESTION_ANSWERING",
        )
    if binding.provider == ModelProviderType.HUGGINGFACE:
        return HuggingFaceEmbeddingProvider(model=binding.provider_model_id)
    raise ValueError(f"Unsupported embedding provider: {binding.provider}")


async def _build_google_stt_runtime(
    *,
    binding: ModelProviderBinding,
    model: ModelRegistry,
    merged_config: dict[str, Any],
    credentials_payload: dict[str, Any],
) -> Any:
    del model
    project_id = (
        merged_config.get("project_id")
        or credentials_payload.get("project_id")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    if not project_id:
        raise ValueError("Google STT requires project_id or GOOGLE_CLOUD_PROJECT")

    credentials_info = credentials_payload.get("service_account_json") or merged_config.get("service_account_json")
    if isinstance(credentials_info, str) and credentials_info.strip().startswith("{"):
        credentials_info = json.loads(credentials_info)
    credentials_path = (
        credentials_payload.get("service_account_path")
        or merged_config.get("service_account_path")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    )
    if not credentials_info and isinstance(credentials_path, str) and credentials_path.strip().startswith("{"):
        credentials_info = json.loads(credentials_path)
        credentials_path = None
    language_codes = merged_config.get("language_codes") or credentials_payload.get("language_codes")
    if isinstance(language_codes, str):
        language_codes = [item.strip() for item in language_codes.split(",") if item.strip()]
    return GoogleSpeechToTextRuntime(
        project_id=str(project_id),
        model=str(binding.provider_model_id or merged_config.get("model") or "chirp_3"),
        location=str(merged_config.get("location") or credentials_payload.get("location") or "us"),
        credentials_info=credentials_info if isinstance(credentials_info, dict) else None,
        credentials_path=str(credentials_path) if credentials_path else None,
        language_codes=language_codes if isinstance(language_codes, list) else None,
    )


def register_default_model_runtime_adapters() -> None:
    chat_providers = (
        ModelProviderType.OPENAI,
        ModelProviderType.XAI,
        ModelProviderType.ANTHROPIC,
        ModelProviderType.GOOGLE,
        ModelProviderType.GEMINI,
    )
    for provider in chat_providers:
        ModelRuntimeAdapterRegistry.register(
            capability=ModelCapabilityType.CHAT,
            provider=provider,
            factory=_build_chat_langchain_runtime,
        )
        ModelRuntimeAdapterRegistry.register(
            capability=ModelCapabilityType.COMPLETION,
            provider=provider,
            factory=_build_chat_langchain_runtime,
        )
        ModelRuntimeAdapterRegistry.register(
            capability=ModelCapabilityType.VISION,
            provider=provider,
            factory=_build_chat_langchain_runtime,
        )

    for provider in (ModelProviderType.OPENAI, ModelProviderType.GOOGLE, ModelProviderType.GEMINI, ModelProviderType.HUGGINGFACE):
        ModelRuntimeAdapterRegistry.register(
            capability=ModelCapabilityType.EMBEDDING,
            provider=provider,
            factory=_build_embedding_runtime,
        )

    ModelRuntimeAdapterRegistry.register(
        capability=ModelCapabilityType.SPEECH_TO_TEXT,
        provider=ModelProviderType.GOOGLE,
        factory=_build_google_stt_runtime,
    )
