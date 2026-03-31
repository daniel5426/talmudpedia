# Execution Plan: RAG Extreme Test Campaign

Last Updated: 2026-03-30

## Status: In Progress

## Goal

Create a repeatable, live-capable test environment for the RAG domain, then drive a broad matrix over:
- every built-in RAG operator
- mixed operator chains
- ingestion and retrieval pipelines
- runtime-input variants
- knowledge-store backends and credential paths
- user-facing builder/runtime UX friction

This plan is about production-readiness validation, not fixes.

## Environment Baseline

Prepared on 2026-03-30:
- backend test profile now exists at `backend/.env.test`
- local pgvector container is reachable at `127.0.0.1:65432` and has the `vector` extension
- local Crawl4AI is reachable at `http://127.0.0.1:11235/health`
- real-db tenant resolution works for `TEST_TENANT_EMAIL`
- active chat and embedding model IDs are pinned in `backend/.env.test`
- local backend API is not currently running on `http://127.0.0.1:8000`

## Current Constraints

- live-provider runs still depend on shell-sourced secrets from `backend/.env`
- Pinecone live coverage is available from env credentials, but should be an opt-in slice after local pgvector parity is stable
- local backend API smoke coverage requires starting the backend process explicitly
- existing RAG coverage is fragmented across graph mutation, crawler, artifact runtime, and agent-side retrieval smoke tests

## Environment Entry Points

Primary prep command:

```bash
backend/scripts/dev-services/prepare_rag_test_env.sh
```

Core focused command pattern:

```bash
cd /Users/danielbenassaya/Code/personal/talmudpedia/backend
set -a
source .env
source .env.test
set +a
PYTHONPATH=. pytest -q <target>
```

## Test Campaign Structure

### 1. Environment and Dependency Validation

- verify pgvector upsert/query/delete lifecycle against the dedicated local pgvector instance
- verify Crawl4AI live crawl success, timeout, invalid URL, depth/page-limit behavior
- verify embedding/provider availability for the pinned tenant models
- verify knowledge-store credential fallback order for pgvector and Pinecone

### 2. Operator-Level Matrix

For each RAG operator:
- valid minimal config
- valid full config
- missing required config
- invalid config types
- empty input
- malformed upstream payload
- runtime override vs saved config precedence
- output-contract shape validation

### 3. Pipeline Topology Matrix

- single-path ingestion pipelines
- single-path retrieval pipelines
- long mixed pipelines with normalization/enrichment/chunking/embedding/storage
- retrieval chains with query input, retrieval, reranking, terminal result
- pipelines with custom operators in the middle and at boundaries
- pipelines with artifact-backed operators mixed with built-ins
- invalid topologies that should fail at analysis/compile time

### 4. Backend Matrix

- pgvector happy path and failure path
- Pinecone happy path and failure path
- namespace handling across sink and retrieval
- store metric updates
- dimension mismatch behavior
- index/collection bootstrap behavior

### 5. Runtime and API Matrix

- compile then execute from persisted visual pipeline
- runtime-input form contract vs executor-required inputs
- table-side run flow
- job status transitions
- per-step input/output persistence
- terminal output shaping
- graph patch and node-config mutation flows

### 6. UX and Product-Fit Review

- nodes whose contracts are too ambiguous to test cleanly
- duplicated or overlapping node surfaces
- builder/runtime mismatch
- naming issues
- settings that are hard to understand or too low-level
- places where two nodes should likely become one surface

## Recommended Execution Order

1. real-db smoke for existing retrieval path
2. live local pgvector + Crawl4AI smoke
3. operator contract matrix
4. pipeline topology matrix
5. API/live backend matrix
6. Pinecone parity matrix
7. UX/product-fit pass in builder

## Initial Commands

Environment prep:

```bash
backend/scripts/dev-services/prepare_rag_test_env.sh
```

Fast local regression slices:

```bash
cd backend && PYTHONPATH=. pytest -q tests/rag_web_crawler tests/graph_mutation_rag tests/rag_artifact_runtime
```

Real-db retrieval smoke:

```bash
cd backend && PYTHONPATH=. pytest -q tests/agent_builder_nodes/test_nodes_execute.py::test_rag_and_vector_search_execute
```

Later live API slice once backend is running:

```bash
cd backend && PYTHONPATH=. pytest -q tests/platform_architect_e2e/test_architect_e2e_live.py -m real_db
```

## Findings Log

All bugs, product gaps, edge-case failures, and UX issues discovered during the campaign should be recorded in:

- `docs/exec-plans/active/rag_extreme_test_gap_log.md`
