from app.services.model_runtime.adapters import register_default_model_runtime_adapters
from app.services.model_runtime.interfaces import (
    ChatRuntime,
    EmbeddingRuntime,
    SpeechToTextResult,
    SpeechToTextRuntime,
    TextToSpeechResult,
    TextToSpeechRuntime,
)
from app.services.model_runtime.registry import ModelRuntimeAdapterRegistry
from app.services.model_runtime.types import ResolvedModelRuntimeExecution

__all__ = [
    "ChatRuntime",
    "EmbeddingRuntime",
    "ModelRuntimeAdapterRegistry",
    "ResolvedModelRuntimeExecution",
    "SpeechToTextResult",
    "SpeechToTextRuntime",
    "TextToSpeechResult",
    "TextToSpeechRuntime",
    "register_default_model_runtime_adapters",
]
