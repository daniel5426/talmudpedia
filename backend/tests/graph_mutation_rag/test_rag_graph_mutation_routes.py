from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routers import rag_graph_mutations as router
from app.services.graph_mutation_service import GraphMutationError


class _ExplodingRagService:
    async def apply_patch(self, *args, **kwargs):
        exc = RuntimeError("post-commit compile failed")
        setattr(exc, "graph_mutation_phase", "post_write_validation")
        raise exc


class _NotFoundRagService:
    async def get_graph(self, *args, **kwargs):
        raise GraphMutationError(
            [{"code": "RAG_PIPELINE_NOT_FOUND", "message": "Pipeline was not found"}]
        )


@pytest.mark.asyncio
async def test_apply_pipeline_graph_patch_returns_structured_internal_error(monkeypatch):
    async def _resolve_service(**kwargs):
        return _ExplodingRagService()

    monkeypatch.setattr(router, "_resolve_service", _resolve_service)

    with pytest.raises(HTTPException) as exc_info:
        await router.apply_pipeline_graph_patch(
            SimpleNamespace(headers={"X-Request-ID": "req-rag-500"}),
            uuid4(),
            router.GraphPatchRequest(operations=[]),
            None,
            {"user": None},
            {},
            None,
        )

    detail = exc_info.value.detail
    assert exc_info.value.status_code == 500
    assert detail["code"] == "GRAPH_MUTATION_INTERNAL_ERROR"
    assert detail["request_id"] == "req-rag-500"
    assert detail["operation"] == "rag.graph.apply_patch"
    assert detail["phase"] == "post_write_validation"
    assert detail["error_class"] == "RuntimeError"


@pytest.mark.asyncio
async def test_get_pipeline_graph_returns_not_found_graph_error(monkeypatch):
    async def _resolve_service(**kwargs):
        return _NotFoundRagService()

    monkeypatch.setattr(router, "_resolve_service", _resolve_service)

    with pytest.raises(HTTPException) as exc_info:
        await router.get_pipeline_graph(
            SimpleNamespace(headers={"X-Request-ID": "req-rag-404"}),
            uuid4(),
            None,
            {"user": None},
            {},
            None,
        )

    detail = exc_info.value.detail
    assert exc_info.value.status_code == 404
    assert detail["code"] == "RAG_PIPELINE_NOT_FOUND"
    assert detail["request_id"] == "req-rag-404"
    assert detail["operation"] == "rag.graph.get"
    assert detail["errors"][0]["code"] == "RAG_PIPELINE_NOT_FOUND"
