# Agent Builder Runtime-Adapter Implementation Summary

Last Updated: 2026-02-10

## Overview
This document summarizes the implementation of the runtime‑agnostic agent builder architecture with LangGraph as **one adapter**, the introduction of GraphSpec v1, and the migration to a GraphIR‑based compiler and execution flow.

## What Was Implemented

### 1) Runtime‑Agnostic Execution Layer
- Introduced a **GraphIR** model as the compiler output.
- Added a **RuntimeAdapter** interface and a runtime registry.
- Implemented **LangGraphAdapter** as the default adapter.
- Execution service now compiles **GraphIR → adapter executable** and consumes **platform‑normalized events** only.

Key files:
- `backend/app/agent/graph/ir.py`
- `backend/app/agent/runtime/base.py`
- `backend/app/agent/runtime/registry.py`
- `backend/app/agent/runtime/langgraph_adapter.py`
- `backend/app/agent/graph/node_factory.py`

### 2) GraphSpec Versioning (Baseline + v2 Extension)
- Backend now accepts `spec_version` and normalizes legacy fields:
  - `sourceHandle` → `source_handle`
  - `targetHandle` → `target_handle`
  - `inputMappings` → `input_mappings`
- GraphSpec v1 remains the baseline contract across FE/BE/SDK.
- GraphSpec v2 orchestration is now a supported extension for node types:
  - `spawn_run`, `spawn_group`, `join`, `router`, `judge`, `replan`, `cancel_subtree`
- Version rule: orchestration v2 nodes require `spec_version="2.0"` and must never be downgraded on save.

Key files:
- `backend/app/agent/graph/schema.py`
- `backend/app/api/schemas/agents.py`
- `backend/documentations/graphspec_v1.md`

### 3) Compiler Outputs GraphIR and Validates Routing
- Compiler now produces **GraphIR** instead of a runtime‑bound executable.
- Added routing validation for conditional nodes (missing/duplicate handles).
- Added GraphSpec version validation.
- Normalized legacy node types (`input`, `output`, `llm_call`, `tool_call`, `rag_retrieval`).

Key files:
- `backend/app/agent/graph/compiler.py`

### 4) Conditional Routing + HITL Approve/Reject
- Routing is compiler‑driven via GraphIR routing maps.
- HITL is now **approve/reject** with strict payload handling.
- Frontend handle IDs updated to `approve` / `reject`.

Key files:
- `backend/app/agent/executors/interaction.py`
- `frontend/src/components/agent-builder/nodes/BaseNode.tsx`

### 5) Unified Execution Engine for `/execute`
- `/agents/{id}/execute` now runs through `AgentExecutorService` and persists runs/traces.
- Removed old stub execution semantics from `AgentService.execute_agent`.

Key files:
- `backend/app/services/agent_service.py`

### 6) Frontend Serialization, Runtime Overlay, and Artifact Mapping
- Graph save normalization is now version-aware:
  - preserve incoming `spec_version` where possible
  - force `2.0` when v2 orchestration nodes exist
- Graph save still normalizes legacy handles/mappings.
- Artifact input mappings are now rendered and stored in config.
- Builder Execute mode now renders an ephemeral runtime topology overlay from orchestration SSE events plus `/agents/runs/{run_id}/tree` reconciliation.
- Runtime topology is execute-only and excluded from persisted `graph_definition`.
- Orchestration config UX now supports Simple/Advanced authoring with preflight validation, structured `scope_subset` and `targets` editing, and route-table authoring for `router`/`judge`.

Key files:
- `frontend-reshet/src/app/admin/agents/[id]/builder/page.tsx`
- `frontend-reshet/src/components/agent-builder/AgentBuilder.tsx`
- `frontend-reshet/src/components/agent-builder/ConfigPanel.tsx`
- `frontend-reshet/src/components/agent-builder/NodeCatalog.tsx`
- `frontend-reshet/src/components/agent-builder/types.ts`

### 7) Event Normalization & Trace Persistence
- Platform emits and persists `node_start` / `node_end` events (not LangGraph events).
- Added retrieval event emission in platform emitter.

Key files:
- `backend/app/agent/execution/service.py`
- `backend/app/agent/execution/emitter.py`

### 8) Fixes / Cleanups
- `ClassifyNodeExecutor` fixed missing imports and message formatting.
- Tests updated for GraphIR output and new trace event types.

Key files:
- `backend/app/agent/executors/classify_executor.py`
- `backend/tests/test_agent_compiler.py`
- `backend/tests/test_full_artifact_layers.py`
- `backend/tests/test_pinecone_openai_rag.py`
- `backend/tests/test_agent_full_system.py`

## Tests Run
- `pytest -q backend/tests/test_agent_compiler.py`

## Architectural Outcome
- **LangGraph is now only an adapter**, not the core execution engine.
- The compiler and execution service are runtime‑agnostic.
- GraphSpec v1 is the baseline data contract, with GraphSpec v2 orchestration as an explicit extension.

## Next Possible Steps

### 1) End‑to‑End HITL UX
- Add frontend UI to **render approve/reject** controls.
- Pass `{ approval, comment }` payload via `/agents/{id}/stream` resume path.

### 2) Multi‑Runtime Support
- Add a second adapter (e.g. “simple_runtime”) to prove runtime independence.
- Implement adapter selection per agent or per tenant.

### 3) SDK Alignment
- Ensure SDK plan validation uses **GraphSpec v1** and compiler validation.
- Expose GraphSpec v1 in SDK documentation + client‑side validation.

### 4) Validation Hardening
- Reject missing `source_handle` on conditional edges in save/publish flows.
- Add migration tool for legacy graphs.

### 5) Expand Tests
- Integration tests for:
  - If/Else routing
  - While loop routing
  - Classify routing
  - UserApproval pause/resume
  - `/execute` facade completion and run persistence

### 6) Runtime Observability
- Normalize additional event types (tool start/end, retrieval) into platform schema.
- Add consistent event taxonomy for SDK clients.

---

If you want, I can execute any of the next steps immediately and extend this summary with new results.
