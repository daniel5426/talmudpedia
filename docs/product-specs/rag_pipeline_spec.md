# RAG Pipeline Spec

Last Updated: 2026-03-23

This document is the canonical product contract for the RAG pipeline builder/runtime surface.

## Purpose

The RAG pipeline spec defines the contract shared by:
- RAG pipeline builder UI
- backend analysis and validation
- backend compilation and runtime execution

## Current Direction

RAG pipelines are not being redesigned around agent `Start` / `End` nodes.

The current direction is:
- keep the RAG operator/pipeline model
- harden it with the same contract discipline introduced in the agent workflow refactor
- make operator registry metadata the authoritative source for builder/runtime contracts

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

## Operator Registry Authority

The backend operator registry is the source of truth for:
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

Validation should fail on contract drift rather than relying on permissive fallback behavior.

## Runtime Contract

Runtime execution must honor the same declared contracts seen by the builder and analysis layers.

Implications:
- runtime input handling must align with required input declarations
- produced operator outputs must match declared output fields
- terminal output materialization must follow the declared pipeline output contract

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

## Canonical Implementation References

- `backend/app/rag/pipeline/registry.py`
- `backend/app/rag/pipeline/compiler.py`
- `backend/app/rag/pipeline/executor.py`
- `backend/app/rag/pipeline/operator_executor.py`
- `backend/app/api/routers/rag_pipelines.py`
- `backend/app/api/routers/rag_operator_contracts.py`
