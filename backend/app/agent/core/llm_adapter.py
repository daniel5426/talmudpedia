from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, List, Optional
import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult, ChatGeneration
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun

from app.agent.core.interfaces import LLMProvider

logger = logging.getLogger(__name__)


def _maybe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _usage_from_mapping(mapping: dict[str, Any] | None) -> dict[str, int] | None:
    if not isinstance(mapping, dict):
        return None

    normalized = {
        "input_tokens": _maybe_int(
            mapping.get("input_tokens")
            or mapping.get("prompt_tokens")
            or mapping.get("prompt_token_count")
            or mapping.get("input_token_count")
            or mapping.get("inputTokenCount")
        ),
        "output_tokens": _maybe_int(
            mapping.get("output_tokens")
            or mapping.get("completion_tokens")
            or mapping.get("candidates_token_count")
            or mapping.get("output_token_count")
            or mapping.get("outputTokenCount")
            or mapping.get("candidatesTokenCount")
        ),
        "total_tokens": _maybe_int(
            mapping.get("total_tokens")
            or mapping.get("usage_tokens")
            or mapping.get("total_token_count")
            or mapping.get("totalTokenCount")
        ),
        "cached_input_tokens": _maybe_int(
            mapping.get("cached_input_tokens")
            or mapping.get("cache_read_input_tokens")
            or mapping.get("cached_content_token_count")
            or mapping.get("cachedContentTokenCount")
        ),
        "cached_output_tokens": _maybe_int(
            mapping.get("cached_output_tokens")
            or mapping.get("cache_write_output_tokens")
            or mapping.get("cachedOutputTokenCount")
        ),
        "reasoning_tokens": _maybe_int(
            mapping.get("reasoning_tokens")
            or mapping.get("thoughts_token_count")
            or mapping.get("reasoningTokenCount")
            or mapping.get("thoughtsTokenCount")
        ),
    }
    if normalized["total_tokens"] is None and normalized["input_tokens"] is not None and normalized["output_tokens"] is not None:
        normalized["total_tokens"] = normalized["input_tokens"] + normalized["output_tokens"]
    payload = {key: value for key, value in normalized.items() if value is not None}
    return payload or None


def extract_usage_payload_from_response_metadata(metadata: Any) -> dict[str, int] | None:
    if not isinstance(metadata, dict):
        return None

    candidates: list[dict[str, Any]] = [metadata]
    for key in ("usage", "usage_metadata", "usageMetadata", "token_usage", "tokenUsage"):
        nested = metadata.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)

    for candidate in candidates:
        payload = _usage_from_mapping(candidate)
        if payload:
            return payload
    return None


def extract_usage_payload_from_message(message: Any) -> dict[str, int] | None:
    direct_usage = getattr(message, "usage_metadata", None)
    payload = _usage_from_mapping(direct_usage if isinstance(direct_usage, dict) else None)
    if payload:
        return payload
    metadata = getattr(message, "response_metadata", None)
    return extract_usage_payload_from_response_metadata(metadata)


@dataclass
class _NormalizedMessagePayload:
    text: str = ""
    content_blocks: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_chunks: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    server_tool_results: list[dict[str, Any]] = field(default_factory=list)
    response_metadata: dict[str, Any] = field(default_factory=dict)
    usage_metadata: dict[str, Any] = field(default_factory=dict)


def _normalize_citation(annotation: Any) -> dict[str, Any] | None:
    if not isinstance(annotation, dict) or annotation.get("type") != "citation":
        return None
    return {
        key: value
        for key, value in annotation.items()
        if value is not None
    }


def _normalize_tool_call_shape(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    normalized = {
        key: value
        for key, value in item.items()
        if key in {"id", "name", "args", "index"}
        and value is not None
    }
    if normalized and "id" not in normalized:
        normalized["id"] = None
    return normalized or None


def _sanitize_content_block(block: Any) -> dict[str, Any] | None:
    if not isinstance(block, dict):
        return None
    normalized = dict(block)
    block_type = normalized.get("type")
    if block_type in {"tool_call", "tool_call_chunk", "server_tool_call", "server_tool_call_chunk"}:
        normalized.setdefault("id", None)
    return normalized


def _coerce_content_blocks(message: Any) -> list[dict[str, Any]]:
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        normalized_blocks = additional_kwargs.get("normalized_content_blocks")
        if isinstance(normalized_blocks, list) and normalized_blocks:
            return [
                normalized
                for block in normalized_blocks
                if (normalized := _sanitize_content_block(block)) is not None
            ]

    raw_content = getattr(message, "content", None)
    if isinstance(raw_content, list) and raw_content and all(isinstance(item, dict) for item in raw_content):
        return [
            normalized
            for block in raw_content
            if (normalized := _sanitize_content_block(block)) is not None
        ]

    blocks = getattr(message, "content_blocks", None)
    if isinstance(blocks, list) and blocks:
        return [
            normalized
            for block in blocks
            if (normalized := _sanitize_content_block(block)) is not None
        ]

    content = raw_content
    if isinstance(content, str) and content:
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        normalized: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, dict):
                sanitized = _sanitize_content_block(item)
                if sanitized is not None:
                    normalized.append(sanitized)
            elif isinstance(item, str):
                normalized.append({"type": "text", "text": item})
        if normalized:
            return normalized

    tool_calls = getattr(message, "tool_calls", None)
    if isinstance(tool_calls, list) and tool_calls:
        normalized_calls: list[dict[str, Any]] = []
        for call in tool_calls:
            normalized_call = _sanitize_content_block(call)
            if normalized_call is None:
                continue
            normalized_call.setdefault("type", "tool_call")
            normalized_call.setdefault("id", None)
            normalized_calls.append(normalized_call)
        if normalized_calls:
            return normalized_calls

    reasoning = None
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        reasoning = additional_kwargs.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        return [{"type": "reasoning", "reasoning": reasoning}]
    return []


def _normalize_message_payload(message: Any) -> _NormalizedMessagePayload:
    payload = _NormalizedMessagePayload()
    payload.content_blocks = _coerce_content_blocks(message)
    metadata = getattr(message, "response_metadata", None)
    if isinstance(metadata, dict):
        payload.response_metadata = dict(metadata)
    usage_metadata = getattr(message, "usage_metadata", None)
    if isinstance(usage_metadata, dict):
        payload.usage_metadata = dict(usage_metadata)

    for block in payload.content_blocks:
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if text is not None:
                payload.text += str(text)
            annotations = block.get("annotations")
            if isinstance(annotations, list):
                for annotation in annotations:
                    citation = _normalize_citation(annotation)
                    if citation is not None:
                        payload.citations.append(citation)
            continue
        if block_type == "reasoning":
            reasoning = block.get("reasoning")
            if isinstance(reasoning, list):
                payload.reasoning += "".join(str(item) for item in reasoning)
            elif reasoning is not None:
                payload.reasoning += str(reasoning)
            continue
        if block_type in {"tool_call", "server_tool_call"}:
            normalized_call = _normalize_tool_call_shape(block)
            if normalized_call:
                payload.tool_calls.append(normalized_call)
            continue
        if block_type in {"tool_call_chunk", "server_tool_call_chunk"}:
            normalized_chunk = _normalize_tool_call_shape(block)
            if normalized_chunk:
                payload.tool_call_chunks.append(normalized_chunk)
            continue
        if block_type == "server_tool_result":
            payload.server_tool_results.append(
                {key: value for key, value in block.items() if value is not None}
            )

    tool_calls = getattr(message, "tool_calls", None)
    if isinstance(tool_calls, list):
        for call in tool_calls:
            normalized_call = _normalize_tool_call_shape(call)
            if normalized_call and normalized_call not in payload.tool_calls:
                payload.tool_calls.append(normalized_call)
    tool_call_chunks = getattr(message, "tool_call_chunks", None)
    if isinstance(tool_call_chunks, list):
        for chunk in tool_call_chunks:
            normalized_chunk = _normalize_tool_call_shape(chunk)
            if normalized_chunk and normalized_chunk not in payload.tool_call_chunks:
                payload.tool_call_chunks.append(normalized_chunk)

    if not payload.text:
        content = getattr(message, "content", None)
        if content is not None:
            payload.text = LLMProviderAdapter._stringify_content(content)

    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict) and not payload.reasoning:
        reasoning = additional_kwargs.get("reasoning_content")
        if isinstance(reasoning, str):
            payload.reasoning = reasoning
    return payload

class LLMProviderAdapter(BaseChatModel):
    """
    Adapter that wraps an LLMProvider and exposes it as a LangChain BaseChatModel.
    Ensures that tokens are correctly emitted to LangChain/LangGraph callbacks
    even during non-streaming 'ainvoke' calls.
    """
    # Use model_config for Pydantic v2
    model_config = {"arbitrary_types_allowed": True}
    
    # Store provider as a private attribute to avoid Pydantic validation issues
    _provider: Any = None
    
    def __init__(self, provider: LLMProvider, **kwargs: Any):
        super().__init__(**kwargs)
        # Use object.__setattr__ to bypass Pydantic's attribute setting
        object.__setattr__(self, '_provider', provider)
    
    @property
    def provider(self) -> Any:
        return self._provider

    @property
    def _llm_type(self) -> str:
        return "llm_provider_adapter"

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("Use _agenerate instead")

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Implementation of generate that uses streaming internally to emit tokens
        to the callback manager, enabling LangGraph astream_events support.
        """
        aggregated = _NormalizedMessagePayload()

        async for chunk in self._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            message = chunk.message
            normalized = _normalize_message_payload(message)
            aggregated.text += normalized.text
            aggregated.content_blocks.extend(normalized.content_blocks)
            aggregated.tool_calls.extend(normalized.tool_calls)
            aggregated.tool_call_chunks.extend(normalized.tool_call_chunks)
            aggregated.reasoning += normalized.reasoning
            aggregated.citations.extend(normalized.citations)
            aggregated.server_tool_results.extend(normalized.server_tool_results)
            if normalized.response_metadata:
                aggregated.response_metadata = normalized.response_metadata
            if normalized.usage_metadata:
                aggregated.usage_metadata = normalized.usage_metadata

        additional_kwargs: dict[str, Any] = {}
        if aggregated.reasoning:
            additional_kwargs["reasoning_content"] = aggregated.reasoning
        if aggregated.citations:
            additional_kwargs["citations"] = aggregated.citations
        if aggregated.server_tool_results:
            additional_kwargs["server_tool_results"] = aggregated.server_tool_results
        if aggregated.content_blocks:
            additional_kwargs["normalized_content_blocks"] = aggregated.content_blocks

        message_kwargs: dict[str, Any] = {
            "content": aggregated.text,
            "additional_kwargs": additional_kwargs,
            "response_metadata": aggregated.response_metadata,
        }
        if aggregated.usage_metadata:
            message_kwargs["usage_metadata"] = aggregated.usage_metadata
        if aggregated.tool_calls:
            message_kwargs["tool_calls"] = aggregated.tool_calls
        message = AIMessage(**message_kwargs)
        return ChatResult(generations=[ChatGeneration(message=message)])

    @staticmethod
    def _stringify_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if text is not None:
                        parts.append(str(text))
                        continue
                text = getattr(item, "text", None)
                if text is not None:
                    parts.append(str(text))
                    continue
                parts.append(str(item))
            return "".join(parts)
        if content is None:
            return ""
        return str(content)

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ChatGenerationChunk, None]:
        """
        Stream handle that translates provider-specific chunks into LangChain chunks
         and trigger the necessary callbacks for LangGraph.
        """
        system_prompt = kwargs.pop("system_prompt", None)
        
        # Debug noise disabled for production runs
        # logger.info(f"[ADAPTER] Starting _astream. run_manager present: {run_manager is not None}")
        
        try:
            async for chunk in self.provider.stream(messages, system_prompt=system_prompt, **kwargs):
                normalized_message = self._coerce_chunk_to_message(chunk)
                normalized = _normalize_message_payload(normalized_message)

                additional_kwargs: dict[str, Any] = {}
                if normalized.reasoning:
                    additional_kwargs["reasoning_content"] = normalized.reasoning
                if normalized.citations:
                    additional_kwargs["citations"] = normalized.citations
                if normalized.server_tool_results:
                    additional_kwargs["server_tool_results"] = normalized.server_tool_results

                if normalized.content_blocks:
                    additional_kwargs["normalized_content_blocks"] = normalized.content_blocks

                message_kwargs: dict[str, Any] = {
                    "content": normalized.text,
                    "additional_kwargs": additional_kwargs,
                    "response_metadata": normalized.response_metadata,
                }
                if normalized.usage_metadata:
                    message_kwargs["usage_metadata"] = normalized.usage_metadata
                if normalized.tool_calls:
                    message_kwargs["tool_calls"] = normalized.tool_calls
                if normalized.tool_call_chunks:
                    message_kwargs["tool_call_chunks"] = normalized.tool_call_chunks

                msg_chunk = AIMessageChunk(**message_kwargs)
                lc_chunk = ChatGenerationChunk(message=msg_chunk)
                if run_manager and normalized.text:
                    await run_manager.on_llm_new_token(normalized.text, chunk=lc_chunk)
                elif run_manager is None:
                    logger.debug("run_manager is None, skipping on_llm_new_token")
                yield lc_chunk
        except Exception as e:
            logger.error(f"Error in LLMProviderAdapter stream: {e}")
            raise

    def _coerce_chunk_to_message(self, chunk: Any) -> BaseMessage:
        if isinstance(chunk, BaseMessage):
            return chunk

        block_type = getattr(chunk, "type", None)
        if block_type == "response.output_text.delta":
            return AIMessageChunk(content_blocks=[{"type": "text", "text": getattr(chunk, "delta", "")}])
        if block_type == "response.reasoning_text.delta":
            return AIMessageChunk(content_blocks=[{"type": "reasoning", "reasoning": getattr(chunk, "delta", "")}])
        if block_type == "response.output_text.done":
            return AIMessageChunk(content="")

        if isinstance(chunk, str):
            return AIMessageChunk(content_blocks=[{"type": "text", "text": chunk}])

        raw_tool_calls = getattr(chunk, "tool_calls", None)
        raw_tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
        raw_content = getattr(chunk, "content", None)
        raw_additional_kwargs = getattr(chunk, "additional_kwargs", None)
        raw_response_metadata = getattr(chunk, "response_metadata", None)
        raw_usage_metadata = getattr(chunk, "usage_metadata", None)
        if (
            raw_content is not None
            or isinstance(raw_tool_calls, list)
            or isinstance(raw_tool_call_chunks, list)
        ):
            message_kwargs: dict[str, Any] = {
                "content": self._stringify_content(raw_content),
                "additional_kwargs": dict(raw_additional_kwargs) if isinstance(raw_additional_kwargs, dict) else {},
                "response_metadata": dict(raw_response_metadata) if isinstance(raw_response_metadata, dict) else {},
            }
            if isinstance(raw_usage_metadata, dict):
                message_kwargs["usage_metadata"] = dict(raw_usage_metadata)
            if isinstance(raw_tool_calls, list):
                normalized_tool_calls = [
                    normalized
                    for item in raw_tool_calls
                    if (normalized := _normalize_tool_call_shape(item)) is not None
                ]
                if normalized_tool_calls:
                    message_kwargs["tool_calls"] = normalized_tool_calls
            if isinstance(raw_tool_call_chunks, list):
                normalized_tool_call_chunks = [
                    normalized
                    for item in raw_tool_call_chunks
                    if (normalized := _normalize_tool_call_shape(item)) is not None
                ]
                if normalized_tool_call_chunks:
                    message_kwargs["tool_call_chunks"] = normalized_tool_call_chunks
            return AIMessageChunk(**message_kwargs)

        text = getattr(chunk, "text", None)
        if text is not None:
            return AIMessageChunk(content_blocks=[{"type": "text", "text": text}])

        if hasattr(chunk, "choices") and getattr(chunk, "choices", None):
            try:
                delta = chunk.choices[0].delta
            except Exception:
                delta = None
            blocks: list[dict[str, Any]] = []
            if delta is not None:
                content = getattr(delta, "content", None)
                if content:
                    blocks.append({"type": "text", "text": content})
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    blocks.append({"type": "reasoning", "reasoning": reasoning})
            if blocks:
                return AIMessageChunk(content_blocks=blocks)

        return AIMessageChunk(content=self._stringify_content(chunk))

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> Any:
        """Forward tool binding to the underlying provider if supported."""
        return super().bind_tools(tools, **kwargs)
