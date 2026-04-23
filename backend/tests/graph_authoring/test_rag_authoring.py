from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.control_plane.rag_admin_service import RagAdminService
from app.services.control_plane.errors import ControlPlaneError
from app.graph_authoring.normalizers.rag import normalize_rag_graph_definition
from app.graph_authoring.validators.rag import collect_rag_authoring_issues
from app.rag.pipeline.registry import OperatorRegistry


def test_rag_normalizer_applies_backend_schema_defaults():
    normalized = normalize_rag_graph_definition(
        {
            "nodes": [
                {
                    "id": "crawl",
                    "category": "source",
                    "operator": "web_crawler",
                    "position": {"x": 0, "y": 0},
                    "config": {"start_urls": "https://example.com"},
                },
                {
                    "id": "search",
                    "category": "retrieval",
                    "operator": "vector_search",
                    "position": {"x": 220, "y": 0},
                    "config": {"knowledge_store_id": "ks_123"},
                },
            ],
            "edges": [{"id": "e1", "source": "crawl", "target": "search"}],
        }
    )

    crawl = next(node for node in normalized["nodes"] if node["id"] == "crawl")
    search = next(node for node in normalized["nodes"] if node["id"] == "search")

    assert crawl["config"]["max_depth"] == 2
    assert crawl["config"]["max_pages"] == 100
    assert crawl["config"]["respect_robots_txt"] is True
    assert crawl["config"]["wait_until"] == "networkidle"
    assert search["config"]["top_k"] == 10
    assert search["config"]["similarity_threshold"] == 0.0


def test_rag_authoring_issues_are_path_specific():
    issues = collect_rag_authoring_issues(
        {
            "nodes": [
                {
                    "id": "search",
                    "category": "retrieval",
                    "operator": "vector_search",
                    "position": {"x": 0, "y": 0},
                    "config": {"temperature": 0.3},
                }
            ],
            "edges": [],
        }
    )

    codes_by_path = {(item.get("code"), item.get("path")) for item in issues}
    assert ("UNKNOWN_CONFIG_FIELD", "/nodes/0/config/temperature") in codes_by_path
    assert ("MISSING_REQUIRED_CONFIG", "/nodes/0/config/knowledge_store_id") in codes_by_path


def test_rag_authoring_does_not_require_runtime_query_input_text():
    issues = collect_rag_authoring_issues(
        {
            "nodes": [
                {
                    "id": "query",
                    "category": "input",
                    "operator": "query_input",
                    "position": {"x": 0, "y": 0},
                    "config": {},
                }
            ],
            "edges": [],
        }
    )

    assert not any(item.get("code") == "MISSING_REQUIRED_CONFIG" for item in issues)


def test_web_crawler_operator_contract_accepts_string_or_list_start_urls():
    spec = OperatorRegistry.get_instance().get("web_crawler")
    assert spec is not None

    assert spec.validate_config({"start_urls": "https://example.com"}) == []
    assert spec.validate_config({"start_urls": ["https://example.com", "https://openai.com"]}) == []


def test_rag_write_rejects_unknown_operator_and_unknown_fields():
    service = RagAdminService(db=SimpleNamespace())

    with pytest.raises(ControlPlaneError) as exc_info:
        service._normalize_graph_for_write(
            nodes=[
                {
                    "id": "bad",
                    "category": "retrieval",
                    "operator": "missing_operator",
                    "position": {"x": 0, "y": 0},
                    "config": {"foo": "bar"},
                }
            ],
            edges=[],
            organization_id="org-1",
        )

    detail = exc_info.value.to_payload()
    assert detail["code"] == "VALIDATION_ERROR"
    assert detail["details"]["errors"][0]["code"] == "UNKNOWN_OPERATOR"
