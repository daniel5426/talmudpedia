from __future__ import annotations

from typing import Any, AsyncGenerator, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from app.agent.core.interfaces import LLMProvider
from app.db.postgres.models.registry import ModelProviderType


class LangChainProviderAdapter(LLMProvider):
    """LLMProvider implementation backed by LangChain chat models."""

    def __init__(self, provider: ModelProviderType, model: str, api_key: Optional[str] = None, **kwargs: Any) -> None:
        self.provider = provider
        self.model_name = model
        self.api_key = api_key
        self.model_kwargs = dict(kwargs or {})
        self._base_model = self._build_model()

    def _build_model(self) -> Any:
        if self.provider == ModelProviderType.OPENAI:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                **self.model_kwargs,
            )
        if self.provider in (ModelProviderType.GOOGLE, ModelProviderType.GEMINI):
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except Exception as exc:  # pragma: no cover - import guard
                raise ImportError(
                    "langchain-google-genai is required for Gemini providers"
                ) from exc

            return ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=self.api_key,
                **self.model_kwargs,
            )

        raise ValueError(f"Unsupported provider for LangChain adapter: {self.provider}")

    def _prepare_messages(self, messages: List[BaseMessage], system_prompt: Optional[str]) -> List[BaseMessage]:
        if system_prompt:
            return [SystemMessage(content=system_prompt)] + list(messages)
        return list(messages)

    def _apply_tool_binding(self, tools: Optional[list[Any]]) -> Any:
        if tools:
            return self._base_model.bind_tools(tools)
        return self._base_model

    def _map_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        mapped = dict(kwargs)
        if "max_tokens" in mapped:
            max_tokens = mapped.pop("max_tokens")
            if self.provider == ModelProviderType.OPENAI:
                mapped.setdefault("max_completion_tokens", max_tokens)
            elif self.provider in (ModelProviderType.GOOGLE, ModelProviderType.GEMINI):
                mapped.setdefault("max_output_tokens", max_tokens)
        return mapped

    async def generate(
        self,
        messages: List[BaseMessage],
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseMessage:
        tools = kwargs.pop("tools", None)
        prepared = self._prepare_messages(messages, system_prompt)
        model = self._apply_tool_binding(tools)
        mapped_kwargs = self._map_kwargs(kwargs)

        response = await model.ainvoke(prepared, **mapped_kwargs)
        if isinstance(response, BaseMessage):
            return response
        return AIMessage(content=str(response))

    async def stream(
        self,
        messages: List[BaseMessage],
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        tools = kwargs.pop("tools", None)
        prepared = self._prepare_messages(messages, system_prompt)
        model = self._apply_tool_binding(tools)
        mapped_kwargs = self._map_kwargs(kwargs)

        async for chunk in model.astream(prepared, **mapped_kwargs):
            yield chunk
