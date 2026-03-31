# RAG Node Catalog Refactor Plan

Last Updated: 2026-03-31

## Summary

Refactor the RAG pipeline node catalog to the final 19-node surface while preserving the current product boundary and runtime stability.

Key rules:
- RAG remains a separate product from Agent
- no shared node abstraction work is included
- this is a RAG catalog/runtime cleanup, not an Agent/RAG convergence project
- existing working Agent, RAG, and artifact behavior must remain green unless an intentional RAG catalog change requires an explicit update

## Target Catalog

### Sources
- `local_loader`
- `s3_loader`
- `web_crawler`
- `api_loader`

### Normalization
- `format_normalizer`
- `pii_redactor`

### Enrichment
- `metadata_extractor`
- `entity_recognizer`
- `classifier`
- `llm`

### Chunking
- `chunker`

### Embedding
- `model_embedder`

### Storage
- `knowledge_store_sink`

### Retrieval
- `query_input`
- `vector_search`
- `hybrid_search`
- `reranker`

### Output
- `retrieval_result`

### Utility
- `transform`

## Implementation Direction

### 1. Add missing target nodes
- add `api_loader`
- add `llm`
- add `transform`

### 2. Collapse or replace existing nodes
- replace `token_based_chunker`, `recursive_chunker`, `semantic_chunker`, and `hierarchical_chunker` with `chunker`
- replace `model_reranker` and `cross_encoder_reranker` with `reranker`
- remove `language_detector`
- remove `summarizer` in favor of `llm`

### 3. Preserve nodes that remain valid
- keep `local_loader`
- keep `s3_loader`
- keep `web_crawler`
- keep `format_normalizer`
- keep `pii_redactor`
- keep `metadata_extractor`
- keep `entity_recognizer`
- keep `classifier`
- keep `model_embedder`
- keep `knowledge_store_sink`
- keep `query_input`
- keep `vector_search`
- keep `hybrid_search`
- keep `retrieval_result`

### 4. Keep runtime architecture stable
- keep the current RAG registry, compiler, and executor architecture
- do not merge with Agent architecture
- do not redesign artifacts in this pass

## Execution Order

1. Update the registry surface to support the target catalog shape.
2. Add executors for the new target nodes or rename/merge existing executor behavior into the target nodes.
3. Update compiler and validation assumptions to the new node IDs and config shapes.
4. Update builder/catalog-facing APIs and any generated inventory surfaces.
5. Replace or remove tests tied to retired node IDs only when the replacement node is covered by equivalent or stronger tests.
6. Re-run the RAG campaign and cross-product regression suites.

## Test Plan

This refactor is not complete until all of the following stay green or are intentionally updated with equivalent coverage.

### RAG catalog and runtime
- `backend/tests/rag_extreme_campaign`
- `backend/tests/graph_mutation_rag`
- `backend/tests/rag_artifact_runtime`
- `backend/tests/rag_web_crawler`

### Agent regression guardrails
- `backend/tests/agent_builder_nodes`
- `backend/tests/agent_builder_graphs`
- `backend/tests/agent_graph_validation`
- `backend/tests/node_inventory`

### Artifact/runtime regression guardrails
- `backend/tests/artifact_runtime`
- `backend/tests/artifact_test_runs`
- `backend/tests/platform_architect_artifacts`

### Required new coverage
- catalog test asserting exactly the final 19 RAG node IDs
- config-schema tests for `api_loader`, `llm`, `chunker`, `reranker`, and `transform`
- migration/parity tests proving replaced node behavior is preserved by the new canonical nodes
- compile-time tests for valid and invalid graphs using the new catalog
- live or integration coverage for the new nodes where runtime behavior depends on real providers

## Acceptance Criteria

- RAG catalog matches the final 19-node spec exactly
- removed/replaced node IDs are no longer exposed in the RAG product surface
- all replacement nodes have executor coverage
- compile-time validation aligns with the new catalog
- runtime execution works for ingestion and retrieval flows
- Agent and artifact behavior remain stable outside intentional RAG catalog changes
