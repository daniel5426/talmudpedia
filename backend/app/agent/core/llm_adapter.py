from typing import Any, AsyncGenerator, List, Optional
import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult, ChatGeneration
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun

from app.agent.core.interfaces import LLMProvider

logger = logging.getLogger(__name__)

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
        full_content = ""
        
        # Use our own _astream implementation to ensure consistent token handling
        async for chunk in self._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            full_content += self._stringify_content(chunk.message.content)
            
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=full_content))])

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
                if isinstance(chunk, AIMessageChunk):
                    msg_chunk = chunk
                    content = self._stringify_content(msg_chunk.content)

                    if content != msg_chunk.content:
                        msg_chunk = msg_chunk.model_copy(update={"content": content})

                    lc_chunk = ChatGenerationChunk(message=msg_chunk)
                    if run_manager:
                        if content:
                            await run_manager.on_llm_new_token(content, chunk=lc_chunk)
                    else:
                        logger.debug("run_manager is None, skipping on_llm_new_token")

                    yield lc_chunk
                    continue

                content = ""
                
                reasoning_content = ""

                # 1. Handle OpenAI "responses" API chunks (delta based)
                if hasattr(chunk, "type"):
                    if chunk.type == "response.output_text.delta":
                        content = getattr(chunk, "delta", "")
                    elif chunk.type == "response.reasoning_text.delta":
                        reasoning_content = getattr(chunk, "delta", "")
                    elif chunk.type == "response.output_text.done":
                        continue
                    # Handle reasoning summary events (skip them)
                    elif "reasoning" in chunk.type and "delta" not in chunk.type:
                        continue
                        
                # 2. Handle Gemini chunks
                elif hasattr(chunk, "text"):
                    try:
                        content = chunk.text
                    except Exception:
                        pass
                
                # 3. Handle raw string chunks
                elif isinstance(chunk, str):
                    content = chunk
                
                # 4. Handle standard OpenAI ChatCompletionChunk
                elif hasattr(chunk, "choices") and hasattr(chunk.choices[0], "delta"):
                     delta = chunk.choices[0].delta
                     if hasattr(delta, "content") and delta.content:
                         content = delta.content
                     # Check for deepseek/refined-openai reasoning field
                     if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                         reasoning_content = delta.reasoning_content

                if content:
                    content = self._stringify_content(content)

                if content or reasoning_content:
                    msg_chunk = AIMessageChunk(content=str(content)) # Enforce string
                    if reasoning_content:
                        msg_chunk.additional_kwargs["reasoning_content"] = reasoning_content
                        
                    lc_chunk = ChatGenerationChunk(message=msg_chunk)
                    # Trigger the callback that LangGraph's astream_events monitors
                    if run_manager:
                        # We only stream content tokens to run_manager to avoid confusing it
                        if content:
                            await run_manager.on_llm_new_token(content, chunk=lc_chunk)
                    else:
                        # Suppress noisy warning when run_manager is absent
                        logger.debug("run_manager is None, skipping on_llm_new_token")
                    yield lc_chunk
                    
        except Exception as e:
            logger.error(f"Error in LLMProviderAdapter stream: {e}")
            raise

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> Any:
        """Forward tool binding to the underlying provider if supported."""
        return super().bind_tools(tools, **kwargs)
