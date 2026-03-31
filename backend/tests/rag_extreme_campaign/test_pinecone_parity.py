from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

from app.rag.interfaces.vector_store import VectorDocument
from app.rag.providers.vector_store.pinecone import PineconeVectorStore


def _load_env() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    load_dotenv(backend_dir / ".env", override=False)
    load_dotenv(backend_dir / ".env.test", override=True)


def _require_pinecone_enabled() -> tuple[str, int]:
    _load_env()
    if os.getenv("RAG_EXTREME_ENABLE_PINECONE_TESTS") != "1":
        pytest.skip("Set RAG_EXTREME_ENABLE_PINECONE_TESTS=1 to run Pinecone parity tests.")
    index_name = os.getenv("RAG_EXTREME_PINECONE_INDEX")
    dimension = os.getenv("RAG_EXTREME_PINECONE_DIMENSION")
    if not index_name or not dimension:
        pytest.skip("Set RAG_EXTREME_PINECONE_INDEX and RAG_EXTREME_PINECONE_DIMENSION for Pinecone parity tests.")
    if not os.getenv("PINECONE_API_KEY"):
        pytest.skip("PINECONE_API_KEY is required for Pinecone parity tests.")
    return index_name, int(dimension)


@pytest.mark.asyncio
async def test_pinecone_upsert_query_delete_in_unique_namespace():
    index_name, dimension = _require_pinecone_enabled()
    namespace = f"rag-extreme-{uuid.uuid4().hex[:12]}"
    vector = [0.0] * dimension
    vector[0] = 1.0
    vector[1] = 0.25

    store = PineconeVectorStore()
    doc_id = f"{namespace}-doc"
    try:
        upserted = await store.upsert(
            index_name,
            documents=[
                VectorDocument(
                    id=doc_id,
                    values=vector,
                    metadata={"text": "pinecone parity smoke", "kind": "campaign"},
                )
            ],
            namespace=namespace,
        )
        assert upserted == 1

        results = await store.search(index_name, vector, top_k=3, namespace=namespace, filter={"kind": "campaign"})
        assert results
        assert results[0].id == doc_id
    finally:
        await store.delete(index_name, [doc_id], namespace=namespace)
