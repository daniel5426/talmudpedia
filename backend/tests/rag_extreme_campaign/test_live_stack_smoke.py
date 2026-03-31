from __future__ import annotations

import contextlib
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

import pytest
from dotenv import load_dotenv
from sqlalchemy import select

from app.db.postgres.models.rag import (
    ExecutablePipeline,
    KnowledgeStore,
    PipelineJob,
    PipelineJobStatus,
    RetrievalPolicy,
    StorageBackend,
)
from app.rag.interfaces import WebCrawlerRequest
from app.rag.interfaces.vector_store import VectorDocument
from app.rag.pipeline.executor import PipelineExecutor
from app.rag.providers.crawler.crawl4ai import Crawl4AIProvider
from app.rag.providers.vector_store.pgvector import PgvectorVectorStore
from app.services.model_resolver import ModelResolver
from app.services.retrieval_service import RetrievalService
from tests.agent_builder_helpers import (
    cleanup_retrieval_setup,
    create_retrieval_setup,
    get_embedding_model_slug,
)


def _load_live_test_env() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    load_dotenv(backend_dir / ".env", override=False)
    load_dotenv(backend_dir / ".env.test", override=True)
    os.environ["TALMUDPEDIA_ENV_PROFILE"] = "test"
    os.environ["TALMUDPEDIA_ENV_FILE"] = str(backend_dir / ".env.test")


def _require_live_provider_keys() -> None:
    _load_live_test_env()
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required for live RAG campaign tests.")


def _require_live_embedding_loop_enabled() -> None:
    if os.getenv("RAG_EXTREME_ENABLE_LIVE_EMBEDDING_TESTS") != "1":
        pytest.skip("Set RAG_EXTREME_ENABLE_LIVE_EMBEDDING_TESTS=1 to run deep live embedding/retrieval campaign tests.")


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
    handler = type("CampaignPageHandler", (_StaticPageHandler,), {"body": body})
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


async def _embed_text(db_session, tenant_id, model_id: str, text: str) -> list[float]:
    resolver = ModelResolver(db_session, tenant_id)
    embedder = await resolver.resolve_embedding(model_id)
    embedded = await embedder.embed(text)
    return embedded.values


@pytest.mark.asyncio
async def test_live_crawl4ai_provider_crawls_local_page():
    _load_live_test_env()
    base_url = os.getenv("CRAWL4AI_BASE_URL")
    if not base_url:
        pytest.skip("CRAWL4AI_BASE_URL is required for live crawler smoke.")

    marker = f"RAG-EXTREME-CRAWL-{uuid.uuid4()}"
    html = f"""
    <html>
      <head><title>RAG Extreme Crawl Smoke</title></head>
      <body>
        <main>
          <h1>{marker}</h1>
          <p>This local page validates the live Crawl4AI integration path.</p>
        </main>
      </body>
    </html>
    """

    with _temporary_html_page(html) as url:
        provider = Crawl4AIProvider(base_url=base_url)
        documents = await provider.crawl(
            WebCrawlerRequest(
                start_urls=[url],
                max_pages=1,
                content_preference="html",
            )
        )

    if not documents:
        pytest.xfail("Live Crawl4AI returned an empty document list for a reachable local page.")
    assert any(marker in (doc.content or "") for doc in documents)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_pgvector_retrieval_service_roundtrip(db_session, test_tenant_id, test_user_id, run_prefix):
    _require_live_provider_keys()
    _require_live_embedding_loop_enabled()

    embed_model_id = await get_embedding_model_slug(db_session, test_tenant_id)
    if not embed_model_id:
        pytest.skip("No embedding model available for pgvector smoke.")

    collection_name = f"{run_prefix}_rag_extreme_roundtrip"
    query_text = f"rag extreme semantic roundtrip {run_prefix}"
    vector_store = PgvectorVectorStore()
    store = None

    try:
        values = await _embed_text(db_session, test_tenant_id, embed_model_id, query_text)
        await vector_store.create_index(collection_name, len(values))
        await vector_store.upsert(
            collection_name,
            [
                VectorDocument(
                    id=f"{run_prefix}-doc",
                    values=values,
                    metadata={"text": query_text, "source": "rag-extreme-campaign"},
                )
            ],
        )

        store = KnowledgeStore(
            tenant_id=test_tenant_id,
            name=f"{run_prefix}-rag-extreme-store",
            description="RAG extreme campaign pgvector smoke",
            embedding_model_id=embed_model_id,
            chunking_strategy={},
            retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
            backend=StorageBackend.PGVECTOR,
            backend_config={"collection_name": collection_name},
            created_by=test_user_id,
        )
        db_session.add(store)
        await db_session.commit()
        await db_session.refresh(store)

        results = await RetrievalService(db_session).query(store.id, query_text, top_k=3)

        assert results
        assert results[0].text == query_text
        assert results[0].metadata["source"] == "rag-extreme-campaign"
    finally:
        if store is not None:
            await db_session.delete(store)
            await db_session.commit()
        await vector_store.delete_index(collection_name)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_retrieval_pipeline_job_executes_end_to_end(db_session, test_tenant_id, test_user_id, run_prefix):
    _require_live_provider_keys()
    _require_live_embedding_loop_enabled()

    pipeline_id, _store_id, collection_name = await create_retrieval_setup(
        db_session, test_tenant_id, test_user_id, run_prefix
    )

    try:
        executable = await db_session.scalar(
            select(ExecutablePipeline).where(ExecutablePipeline.visual_pipeline_id == UUID(pipeline_id))
        )
        assert executable is not None

        job = PipelineJob(
            tenant_id=test_tenant_id,
            executable_pipeline_id=executable.id,
            status=PipelineJobStatus.QUEUED,
            input_params={"text": "hello retrieval", "top_k": 3},
            triggered_by=test_user_id,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        await PipelineExecutor(db_session).execute_job(job.id, artifact_queue_class="artifact_prod_interactive")
        await db_session.refresh(job)

        assert job.status == PipelineJobStatus.COMPLETED
        assert isinstance(job.output, dict)
        assert job.output.get("results")
        assert any(result.get("text") == "hello retrieval" for result in job.output["results"])
    finally:
        await cleanup_retrieval_setup(db_session, pipeline_id, _store_id, collection_name)


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_pgvector_create_index_allows_3072_dimension_without_ivfflat(db_session, test_tenant_id, run_prefix):
    _require_live_provider_keys()

    vector_store = PgvectorVectorStore()
    collection_name = f"{run_prefix}_rag_extreme_large_dim"

    assert await vector_store.create_index(collection_name, 3072) is True

    await vector_store.delete_index(collection_name)
