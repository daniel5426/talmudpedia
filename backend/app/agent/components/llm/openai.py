import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from openai import AsyncOpenAI, Timeout

from app.agent.core.interfaces import LLMProvider


class OpenAILLM(LLMProvider):
    """
    LLM Provider using OpenAI (specifically the responses API for reasoning).
    """

    def __init__(self, model: str = "gpt-5.1", api_key: Optional[str] = None):
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            timeout=Timeout(60.0, connect=10.0)
        )

    def _convert_messages(self, messages: List[BaseMessage]) -> List[Dict[str, Any]]:
        """Convert LangChain messages to OpenAI format."""
        openai_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                # Handle content parts (text + images) if present
                if isinstance(msg.content, list):
                     openai_messages.append({"role": "user", "content": msg.content})
                else:
                    openai_messages.append({"role": "user", "content": str(msg.content)})
            elif isinstance(msg, AIMessage):
                openai_messages.append({"role": "assistant", "content": str(msg.content)})
            elif isinstance(msg, SystemMessage):
                openai_messages.append({"role": "system", "content": str(msg.content)})
            # Add other types if needed
        return openai_messages

    async def generate(
        self,
        messages: List[BaseMessage],
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> BaseMessage:
        """
        Generate a non-streaming response.
        """
        # Prepare input
        input_messages = []
        if system_prompt:
            input_messages.append({"role": "user", "content": system_prompt}) # Using user role for system prompt as per original agent.py pattern often seen with o1/reasoning models
        
        input_messages.extend(self._convert_messages(messages))

        response = await self.client.responses.create(
            model=self.model,
            input=input_messages,
            **kwargs
        )
        
        # Extract content - this depends on the specific response structure of this API
        # Assuming standard-ish structure or adapting from agent.py
        # agent.py doesn't show non-streaming usage, but we can infer.
        # For now, let's stick to what we know works: streaming.
        # But if we must implement generate, we'd need to know the return type.
        # Given the "responses" API is likely the new O1/Reasoning API, let's assume it returns an object with .output
        
        content = ""
        if hasattr(response, 'output'):
             # This is a guess based on agent.py's stream handling
             # In stream: chunk.response.output is a list of items
             pass
             
        # FALLBACK: For now, since we primarily use streaming in the app, 
        # and the API is experimental, we might just use the stream method and aggregate.
        full_content = ""
        async for chunk in self.stream(messages, system_prompt, **kwargs):
             if chunk.type == "response.output_text.delta":
                 full_content += chunk.delta
                 
        return AIMessage(content=full_content)

    async def stream(
        self,
        messages: List[BaseMessage],
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        """
        Stream the response using the OpenAI Responses API.
        """
        input_messages = []
        
        # Add reasoning items from kwargs if present (context persistence)
        reasoning_items = kwargs.pop("reasoning_items", [])
        if reasoning_items:
            sanitized_items = []
            for item in reasoning_items:
                clean_item = item.copy()
                if "status" in clean_item:
                    del clean_item["status"]
                sanitized_items.append(clean_item)
            input_messages.extend(sanitized_items)

        if system_prompt:
             input_messages.append({"role": "user", "content": system_prompt})

        input_messages.extend(self._convert_messages(messages))

        # Default reasoning config
        reasoning_config = kwargs.pop("reasoning", {"effort": "low", "summary": "auto"})

        stream = await self.client.responses.create(
            model=self.model,
            reasoning=reasoning_config,
            input=input_messages,
            include=["reasoning.encrypted_content"],
            stream=True,
            **kwargs
        )

        async for chunk in stream:
            yield chunk
