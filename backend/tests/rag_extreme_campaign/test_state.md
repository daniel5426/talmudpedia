# RAG Extreme Campaign Tests

Last Updated: 2026-04-21

## Scope

Initial live-stack campaign coverage for RAG production-readiness:
- local Crawl4AI smoke against a deterministic local page
- local pgvector retrieval roundtrip with a real embedding model
- compiled retrieval pipeline job execution
- explicit regression coverage for the current 3072-dimension pgvector index failure

## Test Files Present

- `test_live_stack_smoke.py`
- `test_deep_live_retrieval_diagnostics.py`
- `test_local_ingestion_and_storage.py`
- `test_admin_graph_and_jobs_api.py`
- `test_pinecone_parity.py`
- `test_mixed_artifact_pipelines.py`
- `test_retrieval_policy_and_input_contracts.py`
- `test_live_crawler_diagnostics.py`
- `test_operator_contract_matrix.py`
- `test_invalid_topology_matrix.py`
- `test_backend_namespace_and_metrics.py`
- `test_executor_persistence_and_failure_states.py`
- `test_backend_credentials_resolution.py`
- `test_backend_failure_matrix.py`
- `test_long_ingestion_chains.py`
- `test_remaining_gap_reproductions.py`

## Key Scenarios Covered

- Crawl4AI can crawl a live local HTTP page and return the page content through the real provider path.
- pgvector can create a collection, upsert an embedded document, and return it through `RetrievalService.query`.
- a compiled retrieval pipeline can execute through `PipelineExecutor` with persisted `PipelineJob` state.
- the current pgvector `ivfflat` > 2000-dimension limitation is reproducible and asserted explicitly.
- local pgvector ingestion/storage roundtrips can run without live embedding providers by using direct vectors.
- `RetrievalService.query_multiple_stores` merge ordering is asserted deterministically.
- DB-backed admin graph patching persists node config changes and version bumps.
- DB-backed admin compile/job creation persists `ExecutablePipeline` and `PipelineJob` rows.
- deep live embedding/retrieval diagnostics are available as bounded opt-in tests.
- Pinecone parity smoke is available as an opt-in namespace-isolated test.
- mixed builtin-plus-artifact RAG pipelines compile with pinned artifact revisions and execute through the artifact runtime.
- retrieval policy helper behavior is now covered for hybrid, keyword-only, recency-boosted, and multi-store failure isolation.
- pipeline input schema/validator behavior is now covered for the current `query_input` runtime-field mismatch.
- detailed live crawler diagnostics now exist as a bounded opt-in content-preference matrix.
- built-in operator contract coverage now checks crawler config parsing, query-input normalization, and empty-vector sink rejection.
- final-catalog coverage now checks the canonical 19 visible RAG node IDs, retirement of the replaced node IDs, and executor coverage for the new canonical nodes.
- operator contract coverage now also checks `format_normalizer`, `transform`, `classifier`, `llm`, and `reranker`.
- invalid pipeline topology coverage now checks missing entry nodes, multiple query inputs, type mismatches, output-node misuse, and unreachable nodes.
- backend namespace handling now checks store-default namespace fallback, runtime namespace override, and runtime `top_k` precedence.
- executor persistence coverage now checks per-step input/output rows, terminal payload shaping, and failed-step status/error persistence.
- credential resolution coverage now checks env fallback, default-provider credential merge behavior, and disabled-credential rejection.
- backend failure coverage now checks missing executor implementations, zero-upsert handling, no-query-vector failures, and post-search threshold filtering.
- long ingestion-chain coverage now checks a six-step source-to-sink flow across crawl, redaction, metadata extraction, chunking, embedding, and storage.
- focused gap reproductions now pin the `model_embedder` query-object rejection, `query_input.top_k` validator mismatch, invalid seeded retrieval shells, and registry/executor parity drift.
- the long ingestion chain now uses the canonical `chunker` node instead of legacy chunker IDs.

## Last Run

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign/test_live_stack_smoke.py`
- Date: 2026-03-30 Asia/Hebron
- Result: Fast-loop baseline is stable (`1 passed, 2 skipped, 1 xfailed`). The large-dimension pgvector regression assertion passes, the crawler smoke hits a known live issue, and deep embedding/retrieval slices are now explicit opt-ins.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign`
- Date: 2026-03-30 Asia/Hebron
- Result: Expanded fast loop is stable (`5 passed, 5 skipped, 1 xfailed`). Local ingestion/storage coverage and DB-backed admin graph/job API coverage now pass in the default campaign run.

- Command: `cd backend && RAG_EXTREME_ENABLE_LIVE_EMBEDDING_TESTS=1 python3 -m pytest -q -rsxX tests/rag_extreme_campaign/test_deep_live_retrieval_diagnostics.py::test_live_embedding_resolution_and_call_complete_within_budget`
- Date: 2026-03-30 Asia/Hebron
- Result: Pass (`1 passed`). Bounded live embedding resolution and call completed within the test budget.

- Command: `cd backend && RAG_EXTREME_ENABLE_LIVE_EMBEDDING_TESTS=1 python3 -m pytest -q -rsxX tests/rag_extreme_campaign/test_deep_live_retrieval_diagnostics.py::test_live_retrieval_pipeline_job_completes_within_budget`
- Date: 2026-03-30 Asia/Hebron
- Result: Pass (`1 passed`). Live retrieval pipeline execution now completes within budget after the query-input/embedder contract fix.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign`
- Date: 2026-03-30 Asia/Hebron
- Result: Current expanded baseline passes (`13 passed, 6 skipped, 1 xfailed`). Mixed artifact pipelines and retrieval policy/input-contract coverage are now part of the default fast loop.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign/test_operator_contract_matrix.py tests/rag_extreme_campaign/test_invalid_topology_matrix.py tests/rag_extreme_campaign/test_backend_namespace_and_metrics.py tests/rag_extreme_campaign/test_executor_persistence_and_failure_states.py tests/rag_extreme_campaign/test_backend_credentials_resolution.py`
- Date: 2026-03-30 Asia/Hebron
- Result: New batch passes (`18 passed`). Operator contracts, invalid topologies, namespace handling, executor persistence, and credential resolution are now covered.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign`
- Date: 2026-03-30 Asia/Hebron
- Result: Current expanded baseline passes (`31 passed, 6 skipped, 1 xfailed`). The default campaign loop now includes operator-matrix, topology, namespace, persistence, and credential-resolution coverage.

- Command: `cd backend && RAG_EXTREME_ENABLE_LIVE_CRAWLER_DIAGNOSTICS=1 python3 -m pytest -q -rsxX tests/rag_extreme_campaign/test_live_crawler_diagnostics.py`
- Date: 2026-03-30 Asia/Hebron
- Result: Known live failure reproduced as `xfail` (`1 xfailed`). Crawl4AI returned no documents for `fit_markdown`, `raw_markdown`, and `html` against a reachable local page.

- Command: `cd backend && RAG_EXTREME_ENABLE_PINECONE_TESTS=1 RAG_EXTREME_PINECONE_INDEX=talmudpedia-test-255ffab6 RAG_EXTREME_PINECONE_DIMENSION=1536 python3 -m pytest -q -rsxX tests/rag_extreme_campaign/test_pinecone_parity.py`
- Date: 2026-03-30 Asia/Hebron
- Result: Pass (`1 passed`). Pinecone upsert/query/delete parity succeeded in an isolated namespace against a live 1536-dimension test index.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign/test_backend_failure_matrix.py tests/rag_extreme_campaign/test_long_ingestion_chains.py`
- Date: 2026-03-30 Asia/Hebron
- Result: New batch passes (`5 passed`). Backend failure paths and long ingestion-chain execution are now covered.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign`
- Date: 2026-03-30 Asia/Hebron
- Result: Current expanded baseline passes (`36 passed, 6 skipped, 1 xfailed`). The default campaign loop now includes failure-matrix and long-ingestion-chain coverage.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign/test_remaining_gap_reproductions.py`
- Date: 2026-03-30 Asia/Hebron
- Result: Focused contract/state checks pass (`5 passed`). The previous query-input/runtime-validator/shell-graph failures are now locked as fixed behavior, and registry/executor parity drift remains isolated in a dedicated file.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign`
- Date: 2026-03-30 Asia/Hebron
- Result: Current expanded baseline passes (`41 passed, 6 skipped, 1 xfailed`). The default campaign loop now includes the focused known-gap reproductions as well.

- Command: `cd backend && RAG_EXTREME_ENABLE_LIVE_CRAWLER_DIAGNOSTICS=1 python3 -m pytest -q -rsxX tests/rag_extreme_campaign/test_live_crawler_diagnostics.py tests/rag_extreme_campaign/test_live_stack_smoke.py::test_live_crawl4ai_provider_crawls_local_page`
- Date: 2026-03-30 Asia/Hebron
- Result: Pass (`2 passed`). Local Crawl4AI live diagnostics and live local-page smoke now pass after loopback URL normalization for the local crawler runtime.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_web_crawler/test_crawl4ai_provider.py tests/rag_extreme_campaign/test_live_stack_smoke.py::test_pgvector_create_index_allows_3072_dimension_without_ivfflat`
- Date: 2026-03-30 Asia/Hebron
- Result: Pass (`9 passed`). The crawler provider now rewrites local loopback URLs and surfaces crawl failures explicitly; pgvector now allows 3072-dimension collections by skipping `ivfflat`.

- Command: `cd backend && python3 -m pytest -q -rsxX tests/rag_extreme_campaign`
- Date: 2026-03-30 Asia/Hebron
- Result: Current expanded baseline passes (`42 passed, 6 skipped`). The previous default `xfail` is gone; the campaign fast loop is fully green under default settings.

- Command: `cd backend && PYTHONPATH=backend python3 -m pytest -q -rsxX backend/tests/rag_extreme_campaign`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (`47 passed, 6 skipped`). The final 19-node RAG catalog is now asserted explicitly, replacement-node coverage is in place, and the default campaign loop is green after the catalog refactor.
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/rag_extreme_campaign/test_admin_graph_and_jobs_api.py`
- Date: 2026-04-21 Asia/Hebron
- Result: Pass (`2 passed`). Admin RAG graph/job routes now use `organization_id` instead of `tenant_slug`.

## Known Gaps / Follow-ups

- Live embedding/provider latency is still not part of the default fast loop.
