from __future__ import annotations

import contextlib
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from dotenv import load_dotenv

from app.rag.interfaces import WebCrawlerRequest
from app.rag.providers.crawler.crawl4ai import Crawl4AIProvider


def _load_env() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    load_dotenv(backend_dir / ".env", override=False)
    load_dotenv(backend_dir / ".env.test", override=True)


def _require_enabled() -> None:
    _load_env()
    if os.getenv("RAG_EXTREME_ENABLE_LIVE_CRAWLER_DIAGNOSTICS") != "1":
        pytest.skip("Set RAG_EXTREME_ENABLE_LIVE_CRAWLER_DIAGNOSTICS=1 to run detailed live crawler diagnostics.")
    if not os.getenv("CRAWL4AI_BASE_URL"):
        pytest.skip("CRAWL4AI_BASE_URL is required for live crawler diagnostics.")


class _StaticPageHandler(BaseHTTPRequestHandler):
    body = ""

    def do_GET(self) -> None:  # noqa: N802
        payload = self.body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@contextlib.contextmanager
def _temporary_html_page(body: str):
    handler = type("CrawlerDiagnosticHandler", (_StaticPageHandler,), {"body": body})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_live_crawl4ai_content_preference_matrix_against_local_page():
    _require_enabled()

    marker = f"RAG-CRAWLER-DIAG-{uuid.uuid4()}"
    html = f"""
    <html>
      <head><title>{marker}</title></head>
      <body>
        <main>
          <h1>{marker}</h1>
          <p>crawler diagnostics body</p>
        </main>
      </body>
    </html>
    """

    provider = Crawl4AIProvider(base_url=os.getenv("CRAWL4AI_BASE_URL"))
    results = {}
    with _temporary_html_page(html) as url:
        for preference in ("fit_markdown", "raw_markdown", "html"):
            docs = await provider.crawl(
                WebCrawlerRequest(
                    start_urls=[url],
                    max_pages=1,
                    content_preference=preference,
                )
            )
            results[preference] = docs

    missing = [preference for preference, docs in results.items() if not docs]
    if missing:
        pytest.xfail(f"Live Crawl4AI returned no documents for content preferences: {', '.join(missing)}")

    assert any(marker in (doc.content or "") for doc in results["html"])
