from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Any, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from app.rag.interfaces import RawDocument, WebCrawlerProvider, WebCrawlerRequest
from app.rag.interfaces.document_loader import DocumentType


class Crawl4AIProvider(WebCrawlerProvider):
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        bearer_token: Optional[str] = None,
        request_timeout_s: float = 30.0,
        poll_interval_s: float = 1.0,
        poll_timeout_s: float = 300.0,
    ):
        resolved_base_url = (base_url or os.getenv("CRAWL4AI_BASE_URL") or "").strip()
        if not resolved_base_url:
            raise ValueError("CRAWL4AI_BASE_URL is required to execute web_crawler")

        self._base_url = resolved_base_url.rstrip("/")
        self._bearer_token = (bearer_token or os.getenv("CRAWL4AI_BEARER_TOKEN") or "").strip() or None
        self._request_timeout_s = request_timeout_s
        self._poll_interval_s = poll_interval_s
        self._poll_timeout_s = poll_timeout_s

    @property
    def provider_name(self) -> str:
        return "crawl4ai"

    async def crawl(self, request: WebCrawlerRequest) -> List[RawDocument]:
        headers = {"Accept": "application/json"}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"

        timeout = httpx.Timeout(self._request_timeout_s)
        async with httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=timeout) as client:
            task_id, immediate_result = await self._submit_job(client, request)
            if immediate_result is not None:
                return self._normalize_documents(immediate_result, request)

            if not task_id:
                raise ValueError("Crawl4AI did not return crawl results or a task identifier")

            result_payload = await self._poll_for_result(client, task_id)
            return self._normalize_documents(result_payload, request)

    async def _submit_job(
        self,
        client: httpx.AsyncClient,
        request: WebCrawlerRequest,
    ) -> tuple[Optional[str], Optional[Any]]:
        payload = self._build_payload(request)

        response = await client.post("/crawl/job", json=payload)
        if response.status_code == 404:
            response = await client.post("/crawl", json=payload)
        response.raise_for_status()

        data = response.json()
        immediate_result = self._extract_result_payload(data)
        if immediate_result is not None:
            return None, immediate_result

        task_id = self._extract_task_id(data)
        return task_id, None

    async def _poll_for_result(self, client: httpx.AsyncClient, task_id: str) -> Any:
        completed_statuses = {"completed", "done", "success", "finished"}
        failed_statuses = {"failed", "error", "cancelled", "canceled"}
        deadline = asyncio.get_running_loop().time() + self._poll_timeout_s

        while True:
            data = await self._fetch_task_status(client, task_id)
            status = str(data.get("status") or data.get("state") or "").strip().lower()
            result_payload = self._extract_result_payload(data)

            if result_payload is not None and (not status or status in completed_statuses):
                return result_payload
            if status in completed_statuses:
                return []
            if status in failed_statuses:
                message = (
                    data.get("error")
                    or data.get("message")
                    or data.get("detail")
                    or f"Crawl4AI crawl failed for task {task_id}"
                )
                raise RuntimeError(str(message))
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Crawl4AI crawl timed out waiting for task {task_id}")
            await asyncio.sleep(self._poll_interval_s)

    async def _fetch_task_status(self, client: httpx.AsyncClient, task_id: str) -> dict[str, Any]:
        response = await client.get(f"/crawl/job/{task_id}")
        if response.status_code == 404:
            response = await client.get(f"/task/{task_id}")
        response.raise_for_status()
        return response.json()

    def _build_payload(self, request: WebCrawlerRequest) -> dict[str, Any]:
        crawler_config: dict[str, Any] = {}
        if request.max_pages is not None:
            crawler_config["limit"] = request.max_pages
        if request.max_depth is not None:
            crawler_config["max_depth"] = request.max_depth
            crawler_config["maxDiscoveryDepth"] = request.max_depth
        if request.respect_robots_txt is not None:
            crawler_config["respect_robots_txt"] = request.respect_robots_txt
        if request.wait_until:
            crawler_config["wait_until"] = request.wait_until
        if request.page_timeout_ms is not None:
            crawler_config["page_timeout"] = request.page_timeout_ms
        if request.scan_full_page is not None:
            crawler_config["scan_full_page"] = request.scan_full_page

        return {
            "urls": [self._normalize_start_url(url) for url in request.start_urls],
            "crawler_config": crawler_config,
        }

    def _normalize_start_url(self, url: str) -> str:
        parsed = urlparse(url)
        crawler_host = (urlparse(self._base_url).hostname or "").strip().lower()
        target_host = (parsed.hostname or "").strip().lower()
        if crawler_host in {"127.0.0.1", "localhost"} and target_host in {"127.0.0.1", "localhost"}:
            host = "host.docker.internal"
            netloc = host
            if parsed.port:
                netloc = f"{host}:{parsed.port}"
            return urlunparse(parsed._replace(netloc=netloc))
        return url

    def _extract_task_id(self, payload: Any) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        for key in ("task_id", "job_id", "id"):
            value = payload.get(key)
            if value:
                return str(value)
        nested = payload.get("data")
        if isinstance(nested, dict):
            return self._extract_task_id(nested)
        return None

    def _extract_result_payload(self, payload: Any) -> Optional[Any]:
        if payload is None:
            return None
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return None

        for key in ("results", "result"):
            value = payload.get(key)
            if value is not None:
                return value

        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("results", "result"):
                value = data.get(key)
                if value is not None:
                    return value

        if any(key in payload for key in ("markdown", "fit_markdown", "html", "cleaned_html", "url")):
            return [payload]
        return None

    def _normalize_documents(self, payload: Any, request: WebCrawlerRequest) -> List[RawDocument]:
        items = self._coerce_items(payload)
        documents: List[RawDocument] = []
        for item in items:
            document = self._normalize_document(item, request)
            if document is not None:
                documents.append(document)
        if not documents:
            failures = self._collect_failures(items)
            if failures:
                raise RuntimeError("; ".join(failures))
        return documents

    def _collect_failures(self, items: List[Any]) -> List[str]:
        failures: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            success = item.get("success")
            error_message = item.get("error_message") or item.get("error") or item.get("message")
            if success is False and error_message:
                failures.append(str(error_message).strip())
        return failures

    def _coerce_items(self, payload: Any) -> List[Any]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("results", "result", "data"):
                nested = payload.get(key)
                if isinstance(nested, list):
                    return nested
            return [payload]
        return [payload]

    def _normalize_document(self, item: Any, request: WebCrawlerRequest) -> Optional[RawDocument]:
        if not isinstance(item, dict):
            content = str(item).strip()
            if not content:
                return None
            return RawDocument(
                id=self._make_doc_id("crawl4ai:unknown", content),
                content=content,
                doc_type=DocumentType.TEXT,
                metadata={"provider": self.provider_name},
            )

        url = str(item.get("url") or item.get("source") or item.get("source_url") or "").strip()
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        title = str(item.get("title") or metadata.get("title") or "").strip() or None
        status = item.get("status") or metadata.get("status")
        content = self._extract_content(item, request.content_preference)

        if not content:
            return None

        doc_type = self._resolve_doc_type(item, request.content_preference)
        doc_id_seed = url or title or content[:100]
        return RawDocument(
            id=self._make_doc_id(doc_id_seed, content),
            content=content,
            doc_type=doc_type,
            metadata={
                "provider": self.provider_name,
                "url": url or None,
                "title": title,
                "status": status,
                "content_preference": request.content_preference,
                **metadata,
            },
            source_path=url or None,
        )

    def _has_markdown(self, item: dict[str, Any]) -> bool:
        markdown = item.get("markdown")
        return markdown is not None or item.get("fit_markdown") is not None

    def _extract_content(self, item: dict[str, Any], content_preference: str) -> str:
        candidates = self._content_candidates(item, content_preference)
        for candidate in candidates:
            text = self._stringify_candidate(candidate)
            if text:
                return text
        return ""

    def _content_candidates(self, item: dict[str, Any], content_preference: str) -> Iterable[Any]:
        markdown = item.get("markdown")
        if content_preference == "raw_markdown":
            return (
                self._extract_nested_markdown(markdown, "raw_markdown"),
                self._extract_markdown(markdown),
                item.get("markdown_v2"),
                item.get("content"),
                item.get("extracted_content"),
                item.get("cleaned_html"),
                item.get("html"),
            )
        if content_preference == "html":
            return (
                item.get("cleaned_html"),
                item.get("html"),
                self._extract_nested_markdown(markdown, "fit_markdown"),
                self._extract_markdown(markdown),
                item.get("content"),
                item.get("extracted_content"),
            )
        if content_preference == "auto":
            return (
                self._extract_nested_markdown(markdown, "fit_markdown"),
                self._extract_markdown(markdown),
                item.get("markdown_v2"),
                item.get("content"),
                item.get("extracted_content"),
                item.get("cleaned_html"),
                item.get("html"),
            )
        return (
            self._extract_nested_markdown(markdown, "fit_markdown"),
            self._extract_markdown(markdown),
            item.get("markdown_v2"),
            item.get("content"),
            item.get("extracted_content"),
            item.get("cleaned_html"),
            item.get("html"),
        )

    def _extract_nested_markdown(self, value: Any, key: str) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return None

    def _resolve_doc_type(self, item: dict[str, Any], content_preference: str) -> DocumentType:
        if content_preference == "html":
            return DocumentType.HTML
        return DocumentType.MARKDOWN if self._has_markdown(item) else DocumentType.HTML

    def _extract_markdown(self, value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("fit_markdown", "raw_markdown", "markdown", "content"):
                candidate = value.get(key)
                if candidate:
                    return candidate
        return value

    def _stringify_candidate(self, candidate: Any) -> str:
        if candidate is None:
            return ""
        if isinstance(candidate, str):
            return candidate.strip()
        return str(candidate).strip()

    def _make_doc_id(self, seed: str, content: str) -> str:
        digest = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
        safe_seed = hashlib.md5(seed.encode("utf-8")).hexdigest()[:8]
        return f"crawl4ai_{safe_seed}_{digest}"
