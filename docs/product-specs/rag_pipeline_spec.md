# RAG Pipeline Spec

Last Updated: 2026-04-01

This document is the canonical product contract for the RAG pipeline builder/runtime surface.

## Purpose

The RAG pipeline spec defines the contract shared by:
- RAG pipeline builder UI
- backend analysis, compile materialization, and runtime execution

## Current Direction

RAG remains a separate pipeline product.

It is not being redesigned around agent `Start` / `End` nodes, and it is not being unified with Agent through a shared node registry or shared node-definition library.

The current direction is:
- keep the RAG operator/pipeline model
- harden it with explicit product contracts
- simplify and polish the RAG node catalog
- allow Agent to consume RAG pipelines as a product surface, not raw RAG internals

## Canonical Contract Principles

RAG pipeline behavior must now be driven by explicit contracts for:
- operator inputs
- operator outputs
- terminal outputs
- runtime-required inputs
- type compatibility between connected operators

These contracts must be shared across:
- analysis responses
- validation responses
- builder pickers/forms
- compiler/runtime execution

## Draft-Legal Persistence

RAG visual pipeline drafts are draft-legal.

Rules:
- save/update persists incomplete drafts
- graph mutation writes reject only illegal mutations
- compile is an explicit executable-materialization step
- run requires a current executable and must not silently recompile

Examples of allowed draft state:
- disconnected nodes
- missing edges
- incomplete retrieval or ingestion branches
- partially configured operators

Examples of write-time rejection:
- unknown config field for an operator
- invalid config-path/container descent
- illegal picker-backed resource selection

## Node Catalog

The canonical RAG pipeline node catalog is:

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

Total: 19 nodes.

## Catalog Direction

The catalog direction is opinionated:
- collapse multiple chunking variants into one `chunker` node with strategy config
- collapse multiple reranking variants into one `reranker` node with strategy/model config
- replace specialized enrichment transforms like `summarizer` with a general-purpose `llm` node
- keep RAG-specific retrieval/storage/source nodes explicit
- keep utility operations explicit through `transform`

## Registry Authority

The backend RAG operator registry is the source of truth for:
- operator config/input surface
- operator output contract
- type metadata used by validation and builder UX

Builder-side hardcoded assumptions should not override registry contracts.

## Input Contract

Analysis and validation responses must identify:
- required runtime inputs
- expected input types
- missing required inputs
- incompatible upstream/downstream mappings

Runtime input forms must be generated from the canonical operator/pipeline contract rather than ad-hoc UI assumptions.

## Output Contract

Each runtime-producing RAG operator must expose an explicit declared output contract.

Baseline output expectations include:
- retrieval/search operators expose structured retrieval outputs such as `results` and `documents`
- transform/enrichment operators expose their transformed payload shape explicitly
- terminal pipeline outputs are declared, not inferred from incidental runtime payloads

Terminal outputs must be explicit enough for:
- builder result wiring
- validation/type checks
- API/runtime response shaping

## Validation Contract

Validation and analysis surfaces must report:
- required runtime inputs
- terminal outputs
- type compatibility issues
- contract mismatches between connected operators

Validation is advisory during editing and becomes a hard failure only when the user explicitly compiles or runs.

## Runtime Contract

Runtime execution must honor the same declared contracts seen by the builder and analysis layers.

Implications:
- runtime input handling must align with required input declarations
- produced operator outputs must match declared output fields
- terminal output materialization must follow the declared pipeline output contract
- a stale executable must return compile-required feedback instead of silently rebuilding on run

## Compatibility Rules

The pipeline system should treat type compatibility as a first-class concern.

Current required behavior:
- operator connections must be checked against declared input/output types
- incompatible mappings should surface in analysis/validation before execution
- runtime should not silently reinterpret incompatible values as a fallback strategy

## Relationship To Agent Graph Contracts

The agent workflow refactor introduced:
- explicit output contracts
- stronger inventory/type discipline
- authoritative final output semantics

RAG parity means applying the same discipline to pipeline operators and terminal outputs without forcing the agent-node model onto RAG.

RAG and Agent stay separate at the node-architecture level:
- no shared registry
- no shared node-definition package
- no projection layer between Agent and RAG specs

Small name overlap between products is acceptable.

## Canonical Implementation References

- `backend/app/rag/pipeline/registry.py`
- `backend/app/rag/pipeline/compiler.py`
- `backend/app/rag/pipeline/executor.py`
- `backend/app/rag/pipeline/operator_executor.py`
- `backend/app/api/routers/rag_pipelines.py`
- `backend/app/api/routers/rag_operator_contracts.py`
