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


@dataclass
class TavilyWebSearchProvider:
    api_key: str
    endpoint: str = "https://api.tavily.com/search"
    timeout_s: int = 15

    async def search(self, *, query: str, top_k: int = 5) -> dict[str, Any]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max(1, min(int(top_k or 5), 20)),
        }
        timeout = httpx.Timeout(self.timeout_s)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self.endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

        rows = data.get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            rows = []

        results = []
        for item in rows[: payload["max_results"]]:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("content") or item.get("snippet"),
                }
            )
        return {
            "query": query,
            "provider": "tavily",
            "results": results,
        }


@dataclass
class ExaWebSearchProvider:
    api_key: str
    endpoint: str = "https://api.exa.ai/search"
    timeout_s: int = 15

    async def search(self, *, query: str, top_k: int = 5) -> dict[str, Any]:
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "numResults": max(1, min(int(top_k or 5), 20)),
        }
        timeout = httpx.Timeout(self.timeout_s)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        rows = data.get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            rows = []

        results = []
        for item in rows[: payload["numResults"]]:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("text") or item.get("snippet"),
                }
            )
        return {
            "query": query,
            "provider": "exa",
            "results": results,
        }


def create_web_search_provider(provider: str, *, api_key: str, endpoint: str | None = None, timeout_s: int = 15) -> WebSearchProvider:
    key = str(provider or "").strip().lower()
    if key == "serper":
        return SerperWebSearchProvider(api_key=api_key, endpoint=endpoint or "https://google.serper.dev/search", timeout_s=timeout_s)
    if key == "tavily":
        return TavilyWebSearchProvider(api_key=api_key, endpoint=endpoint or "https://api.tavily.com/search", timeout_s=timeout_s)
    if key == "exa":
        return ExaWebSearchProvider(api_key=api_key, endpoint=endpoint or "https://api.exa.ai/search", timeout_s=timeout_s)
    raise ValueError(f"Unsupported web search provider: {provider}")
