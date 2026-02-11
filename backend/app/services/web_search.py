from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class WebSearchProvider(Protocol):
    async def search(self, *, query: str, top_k: int = 5) -> dict[str, Any]:
        ...


@dataclass
class SerperWebSearchProvider:
    api_key: str
    endpoint: str = "https://google.serper.dev/search"
    timeout_s: int = 15

    async def search(self, *, query: str, top_k: int = 5) -> dict[str, Any]:
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "q": query,
            "num": max(1, min(int(top_k or 5), 20)),
        }
        timeout = httpx.Timeout(self.timeout_s)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        organic = data.get("organic") if isinstance(data, dict) else None
        if not isinstance(organic, list):
            organic = []

        results = []
        for item in organic[: payload["num"]]:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("link"),
                    "snippet": item.get("snippet"),
                    "position": item.get("position"),
                }
            )

        return {
            "query": query,
            "provider": "serper",
            "results": results,
        }


def create_web_search_provider(provider: str, *, api_key: str, endpoint: str | None = None, timeout_s: int = 15) -> WebSearchProvider:
    key = str(provider or "").strip().lower()
    if key == "serper":
        return SerperWebSearchProvider(api_key=api_key, endpoint=endpoint or "https://google.serper.dev/search", timeout_s=timeout_s)
    raise ValueError(f"Unsupported web search provider: {provider}")
