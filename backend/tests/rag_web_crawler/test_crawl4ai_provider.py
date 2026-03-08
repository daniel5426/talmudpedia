from __future__ import annotations

import httpx
import pytest

from app.rag.interfaces import WebCrawlerRequest
from app.rag.providers.crawler.crawl4ai import Crawl4AIProvider


def _mock_async_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)


@pytest.mark.asyncio
async def test_crawl4ai_provider_omits_auth_header_when_token_is_unset(monkeypatch):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.url.path == "/crawl/job":
            return httpx.Response(404, json={"detail": "not found"})
        if request.url.path == "/crawl":
            return httpx.Response(200, json={"task_id": "task-1"})
        if request.url.path == "/crawl/job/task-1":
            return httpx.Response(404, json={"detail": "not found"})
        if request.url.path == "/task/task-1":
            return httpx.Response(
                200,
                json={"status": "completed", "result": {"results": [{"url": "https://example.com", "markdown": {"fit_markdown": "Hello world"}}]}},
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    _mock_async_client(monkeypatch, handler)

    provider = Crawl4AIProvider(base_url="http://crawl4ai.local")
    docs = await provider.crawl(WebCrawlerRequest(start_urls=["https://example.com"], max_pages=2))

    assert len(docs) == 1
    assert docs[0].content == "Hello world"
    assert requests_seen[0].headers.get("authorization") is None


@pytest.mark.asyncio
async def test_crawl4ai_provider_includes_bearer_header_and_normalizes_results(monkeypatch):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.url.path == "/crawl/job":
            return httpx.Response(
                200,
                json={"task_id": "task-2"},
            )
        if request.url.path == "/crawl/job/task-2":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "result": {
                        "results": [
                            {
                                "url": "https://example.com/page",
                                "title": "Example",
                                "markdown": {"fit_markdown": "# Example"},
                                "metadata": {"language": "en"},
                            }
                        ]
                    },
                },
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    _mock_async_client(monkeypatch, handler)

    provider = Crawl4AIProvider(base_url="http://crawl4ai.local", bearer_token="secret-token")
    docs = await provider.crawl(WebCrawlerRequest(start_urls=["https://example.com/page"], max_depth=2, max_pages=5))

    assert len(docs) == 1
    assert docs[0].metadata["provider"] == "crawl4ai"
    assert docs[0].metadata["title"] == "Example"
    assert docs[0].metadata["content_preference"] == "fit_markdown"
    assert docs[0].source_path == "https://example.com/page"
    assert requests_seen[0].headers["authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_crawl4ai_provider_applies_top_level_crawl_controls(monkeypatch):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.url.path == "/crawl/job":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.com/page",
                            "markdown": {
                                "fit_markdown": "# Fit",
                                "raw_markdown": "# Raw",
                            },
                            "cleaned_html": "<main>Clean</main>",
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    _mock_async_client(monkeypatch, handler)

    provider = Crawl4AIProvider(base_url="http://crawl4ai.local")
    docs = await provider.crawl(
        WebCrawlerRequest(
            start_urls=["https://example.com/page"],
            wait_until="networkidle",
            page_timeout_ms=45000,
            scan_full_page=True,
            content_preference="html",
        )
    )

    sent_payload = requests_seen[0].content.decode("utf-8")
    assert '"wait_until":"networkidle"' in sent_payload
    assert '"page_timeout":45000' in sent_payload
    assert '"scan_full_page":true' in sent_payload
    assert docs[0].content == "<main>Clean</main>"
    assert docs[0].doc_type.value == "html"


@pytest.mark.asyncio
async def test_crawl4ai_provider_raises_timeout_when_task_never_completes(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/crawl/job":
            return httpx.Response(200, json={"task_id": "task-3"})
        if request.url.path == "/crawl/job/task-3":
            return httpx.Response(200, json={"status": "running"})
        raise AssertionError(f"Unexpected path: {request.url.path}")

    _mock_async_client(monkeypatch, handler)

    provider = Crawl4AIProvider(
        base_url="http://crawl4ai.local",
        poll_interval_s=0.0,
        poll_timeout_s=0.0,
    )

    with pytest.raises(TimeoutError, match="timed out"):
        await provider.crawl(WebCrawlerRequest(start_urls=["https://example.com"]))


@pytest.mark.asyncio
async def test_crawl4ai_provider_surfaces_connection_errors(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _mock_async_client(monkeypatch, handler)

    provider = Crawl4AIProvider(base_url="http://crawl4ai.local")
    with pytest.raises(httpx.ConnectError, match="connection refused"):
        await provider.crawl(WebCrawlerRequest(start_urls=["https://example.com"]))


def test_crawl4ai_provider_requires_base_url(monkeypatch):
    monkeypatch.delenv("CRAWL4AI_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="CRAWL4AI_BASE_URL"):
        Crawl4AIProvider()
