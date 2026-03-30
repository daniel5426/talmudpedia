from __future__ import annotations

import json
import os
from typing import Any

import tiktoken
from anthropic import AsyncAnthropic
from google import genai


class TokenCounterService:
    def __init__(self) -> None:
        self._tokenizer_model_fallback = (os.getenv("TOKEN_COUNTER_TIKTOKEN_FALLBACK_MODEL") or "gpt-4o").strip() or "gpt-4o"
        self._tokenizer_encoding_fallback = (os.getenv("TOKEN_COUNTER_TIKTOKEN_FALLBACK_ENCODING") or "cl100k_base").strip() or "cl100k_base"

    async def count_input_tokens(
        self,
        *,
        provider: str | None,
        provider_model_id: str | None,
        snapshot: dict[str, Any],
        api_key: str | None = None,
    ) -> tuple[int | None, str]:
        normalized_provider = str(provider or "").strip().lower()
        normalized_model = str(provider_model_id or "").strip() or None

        if normalized_provider in {"google", "gemini"} and normalized_model:
            counted = await self._count_google(model=normalized_model, snapshot=snapshot, api_key=api_key)
            if counted is not None:
                return counted, "provider_count_api"

        if normalized_provider == "anthropic" and normalized_model:
            counted = await self._count_anthropic(model=normalized_model, snapshot=snapshot, api_key=api_key)
            if counted is not None:
                return counted, "provider_count_api"

        counted = self._count_with_tiktoken(model=normalized_model, snapshot=snapshot)
        if counted is not None:
            return counted, "tokenizer_estimate"
        return None, "unknown"

    async def _count_google(self, *, model: str, snapshot: dict[str, Any], api_key: str | None) -> int | None:
        key = str(api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
        if not key:
            return None

        def _call() -> int | None:
            client = genai.Client(api_key=key)
            contents = self._google_contents(snapshot, include_system_prompt=True)
            response = client.models.count_tokens(model=model, contents=contents)
            total = getattr(response, "total_tokens", None)
            try:
                return int(total) if total is not None else None
            except Exception:
                return None

        import asyncio

        try:
            return await asyncio.to_thread(_call)
        except Exception:
            return None

    async def _count_anthropic(self, *, model: str, snapshot: dict[str, Any], api_key: str | None) -> int | None:
        key = str(api_key or os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not key:
            return None
        client = AsyncAnthropic(api_key=key)
        try:
            response = await client.messages.count_tokens(
                model=model,
                system=str(snapshot.get("system_prompt") or "") or None,
                messages=self._anthropic_messages(snapshot),
                tools=self._anthropic_tools(snapshot) or None,
            )
        except Exception:
            return None
        total = getattr(response, "input_tokens", None)
        try:
            return int(total) if total is not None else None
        except Exception:
            return None

    def _count_with_tiktoken(self, *, model: str | None, snapshot: dict[str, Any]) -> int | None:
        try:
            encoding = tiktoken.encoding_for_model(model or self._tokenizer_model_fallback)
        except Exception:
            try:
                encoding = tiktoken.get_encoding(self._tokenizer_encoding_fallback)
            except Exception:
                return None
        rendered = self._serialize_for_tokenizer(snapshot)
        try:
            return len(encoding.encode(rendered))
        except Exception:
            return None

    @staticmethod
    def _serialize_for_tokenizer(snapshot: dict[str, Any]) -> str:
        try:
            return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return str(snapshot)

    @staticmethod
    def _google_contents(snapshot: dict[str, Any], *, include_system_prompt: bool = False) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        system_prompt = str(snapshot.get("system_prompt") or "").strip()
        if include_system_prompt and system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
        for item in snapshot.get("messages") or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role in {"assistant", "ai", "model"}:
                normalized_role = "model"
            else:
                normalized_role = "user"
            part_text = TokenCounterService._content_to_text(item.get("content"))
            if part_text:
                contents.append({"role": normalized_role, "parts": [{"text": part_text}]})
        return contents

    @staticmethod
    def _anthropic_messages(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for item in snapshot.get("messages") or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role in {"system"}:
                continue
            normalized_role = "assistant" if role in {"assistant", "ai", "model"} else "user"
            content = item.get("content")
            if isinstance(content, list):
                messages.append({"role": normalized_role, "content": content})
                continue
            text = TokenCounterService._content_to_text(content)
            messages.append({"role": normalized_role, "content": text})
        return messages

    @staticmethod
    def _anthropic_tools(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for tool in snapshot.get("tools") or []:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name") or "").strip()
            if not name:
                continue
            payload = {"name": name}
            if tool.get("description") is not None:
                payload["description"] = tool.get("description")
            input_schema = tool.get("input_schema") or tool.get("parameter_schema")
            if isinstance(input_schema, dict):
                payload["input_schema"] = input_schema
            tools.append(payload)
        return tools

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content") or item.get("reasoning")
                    if text is not None:
                        parts.append(str(text))
                else:
                    parts.append(str(item))
            return "".join(parts)
        if isinstance(content, dict):
            text = content.get("text") or content.get("content")
            if text is not None:
                return str(text)
        return str(content)
