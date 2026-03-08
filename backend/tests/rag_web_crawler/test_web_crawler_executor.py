from __future__ import annotations

from typing import List

import pytest

from app.rag.interfaces.document_loader import RawDocument, DocumentType
from app.rag.pipeline.operator_executor import (
    ExecutionContext,
    ExecutorRegistry,
    OperatorInput,
    WebCrawlerExecutor,
)
from app.rag.pipeline.registry import OperatorRegistry


class _FakeProvider:
    def __init__(self, documents: List[RawDocument]):
        self.documents = documents
        self.requests = []

    async def crawl(self, request):
        self.requests.append(request)
        return self.documents


@pytest.mark.asyncio
async def test_web_crawler_executor_uses_runtime_overrides(monkeypatch):
    spec = OperatorRegistry.get_instance().get("web_crawler")
    assert spec is not None

    fake_provider = _FakeProvider(
        [
            RawDocument(
                id="doc-1",
                content="crawl result",
                doc_type=DocumentType.MARKDOWN,
                metadata={"url": "https://runtime.example.com"},
                source_path="https://runtime.example.com",
            )
        ]
    )

    monkeypatch.setattr(WebCrawlerExecutor, "_build_provider", lambda self: fake_provider)
    executor = WebCrawlerExecutor(spec)

    result = await executor.execute(
        OperatorInput(
            data={
                "start_urls": "https://runtime.example.com",
                "max_pages": 5,
                "content_preference": "html",
                "page_timeout_ms": 45000,
            }
        ),
        ExecutionContext(
            step_id="crawler-step",
            config={
                "start_urls": "https://saved.example.com",
                "max_pages": 2,
                "max_depth": 3,
                "wait_until": "networkidle",
                "scan_full_page": True,
            },
        ),
    )

    assert result.success is True
    assert fake_provider.requests[0].start_urls == ["https://runtime.example.com"]
    assert fake_provider.requests[0].max_pages == 5
    assert fake_provider.requests[0].max_depth == 3
    assert fake_provider.requests[0].content_preference == "html"
    assert fake_provider.requests[0].page_timeout_ms == 45000
    assert fake_provider.requests[0].wait_until == "networkidle"
    assert fake_provider.requests[0].scan_full_page is True
    assert result.data[0]["source_path"] == "https://runtime.example.com"


@pytest.mark.asyncio
async def test_web_crawler_executor_rejects_invalid_content_preference(monkeypatch):
    spec = OperatorRegistry.get_instance().get("web_crawler")
    assert spec is not None

    monkeypatch.setattr(WebCrawlerExecutor, "_build_provider", lambda self: _FakeProvider([]))
    executor = WebCrawlerExecutor(spec)

    with pytest.raises(ValueError, match="content_preference must be one of"):
        await executor.execute(
            OperatorInput(data={"start_urls": "https://example.com", "content_preference": "pdf"}),
            ExecutionContext(step_id="crawler-step", config={}),
        )


def test_web_crawler_executor_registry_resolves_builtin_executor():
    spec = OperatorRegistry.get_instance().get("web_crawler")
    assert spec is not None

    executor = ExecutorRegistry.create_executor(spec)
    assert isinstance(executor, WebCrawlerExecutor)


@pytest.mark.asyncio
async def test_web_crawler_executor_rejects_invalid_urls(monkeypatch):
    spec = OperatorRegistry.get_instance().get("web_crawler")
    assert spec is not None

    monkeypatch.setattr(WebCrawlerExecutor, "_build_provider", lambda self: _FakeProvider([]))
    executor = WebCrawlerExecutor(spec)

    with pytest.raises(ValueError, match="Invalid start_urls"):
        await executor.execute(
            OperatorInput(data={"start_urls": "ftp://example.com"}),
            ExecutionContext(step_id="crawler-step", config={}),
        )


@pytest.mark.asyncio
async def test_web_crawler_executor_requires_urls(monkeypatch):
    spec = OperatorRegistry.get_instance().get("web_crawler")
    assert spec is not None

    monkeypatch.setattr(WebCrawlerExecutor, "_build_provider", lambda self: _FakeProvider([]))
    executor = WebCrawlerExecutor(spec)

    with pytest.raises(ValueError, match="requires at least one start URL"):
        await executor.execute(
            OperatorInput(data={}),
            ExecutionContext(step_id="crawler-step", config={}),
        )
