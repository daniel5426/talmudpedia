import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
import google.generativeai as genai

from app.agent.core.interfaces import LLMProvider


class GeminiLLM(LLMProvider):
    """
    LLM Provider using Google Gemini.
    """

    def __init__(self, model: str = "gemini-2.0-flash", api_key: Optional[str] = None):
        self.model_name = model
        genai.configure(api_key=api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        self.model = genai.GenerativeModel(model)

    def _convert_messages(self, messages: List[BaseMessage]) -> List[Any]:
        """Convert LangChain messages to Gemini format."""
        gemini_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                gemini_messages.append({"role": "user", "parts": [str(msg.content)]})
            elif isinstance(msg, AIMessage):
                gemini_messages.append({"role": "model", "parts": [str(msg.content)]})
            elif isinstance(msg, SystemMessage):
                # Gemini doesn't have a system role in all models, but GenerativeModel handles it if passed in init.
                # Here we just treat it as user message if needed, or skip if handled by system_instruction.
                pass
        return gemini_messages

    async def generate(
        self,
        messages: List[BaseMessage],
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> BaseMessage:
        """Generate a response using Gemini."""
        history = self._convert_messages(messages[:-1])
        last_msg = str(messages[-1].content)
        
        # If we have a system prompt, we should ideally use it in the model config
        if system_prompt:
             self.model = genai.GenerativeModel(self.model_name, system_instruction=system_prompt)

        chat = self.model.start_chat(history=history)
        response = await chat.send_message_async(last_msg)
        return AIMessage(content=response.text)

    async def stream(
        self,
        messages: List[BaseMessage],
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        """Stream the response using Gemini."""
        history = self._convert_messages(messages[:-1])
        last_msg = str(messages[-1].content)
        
        if system_prompt:
             self.model = genai.GenerativeModel(self.model_name, system_instruction=system_prompt)

        # Combine history and last message for stateless generation
        full_gemini_messages = self._convert_messages(messages)
        
        print(f"[DEBUG] Gemini generate_content_async with {len(full_gemini_messages)} messages")
        try:
            # Note: generate_content_async expects list of dicts/contents
            response = await self.model.generate_content_async(full_gemini_messages, stream=True)
            print(f"[DEBUG] Gemini generate_content_async returned response object: {type(response)}")
            
            async for chunk in response:
                # print(f"[DEBUG] Gemini chunk received: {type(chunk)}")
                yield chunk
        except Exception as e:
            print(f"[DEBUG] Gemini Error: {e}")
            raise e
