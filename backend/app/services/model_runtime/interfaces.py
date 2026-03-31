from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


class SpeechToTextSegment(BaseModel):
    text: str
    attachment_id: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    confidence: float | None = None


class SpeechToTextResult(BaseModel):
    text: str = ""
    segments: list[SpeechToTextSegment] = Field(default_factory=list)
    language: str | None = None
    attachments: list[str] = Field(default_factory=list)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)


class TextToSpeechResult(BaseModel):
    audio_content: bytes
    mime_type: str = "audio/mpeg"
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)


class ChatRuntime(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[BaseMessage],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> BaseMessage:
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[BaseMessage],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        pass


class EmbeddingRuntime(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def embed(self, text: str) -> Any:
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[Any]:
        pass


class SpeechToTextRuntime(ABC):
    @abstractmethod
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
        pass


class TextToSpeechRuntime(ABC):
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
        **kwargs: Any,
    ) -> TextToSpeechResult:
        pass
