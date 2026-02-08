# Agent Builder Tests: What Was Added and Why

Last Updated: 2026-02-05

## Purpose
This document explains the tests we added for the agent builder and runtime, why they were created, and what kind of tests they are (unit vs. integration vs. full‑stack). These tests were designed to be **gap detectors**: they target known failure modes in the builder and runtime and validate that the full agent execution path works with real services.

## Test Taxonomy (High‑Level)

### 1) Frontend Unit Tests (Jest + React Testing Library)
**Location**: `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/agent_builder/branch_handles.test.tsx`

**Why**: The builder was creating invalid/deduplicated branch handles for `classify` and `if_else` nodes, which breaks edge routing in the UI.

**How**:
- Render `BaseNode` directly (no full ReactFlow context).
- Mock `@xyflow/react`’s `Handle` component to expose handle IDs in the DOM.
- Assert handle IDs for:
  - empty names (fallback to `category_0`, `condition_0`)
  - duplicates (dedupe to `support_1`, `yes_1`)
  - `if_else` always includes `else`.

**Type**: Component-level unit tests (no backend, no network).

---

### 2) Backend Integration Tests (Pytest + Real DB)
**Location**: `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_execution_events/test_node_event_emission.py`

**Why**: Debug streaming previously emitted node events inconsistently for `start`/`human_input`/`end`, making execution tracing unreliable in the UI.

**How**:
- Build a minimal graph: `start → human_input → end`.
- Execute via `AgentExecutorService` in `ExecutionMode.DEBUG`.
- Stream events and assert `node_start` / `node_end` for each node.

**Type**: Backend integration test against the real execution stack.

---

### 3) Backend Full‑Stack “Large Agent” Tests (Pytest + Real DB + External Services)
**Location**: `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_builder_large_agents/test_large_agent_scenarios.py`

**Why**: These simulate real UI‑built agents (10+ nodes), covering routing, guardrails, RAG, tools, approvals, and end‑to‑end execution. They validate that **full flows actually run**, not just compile.

**How**:
- Build multi‑node graphs using helper builders (`graph_def`, `node_def`, `edge_def`).
- Require real dependencies:
  - OpenAI chat model registered in `ModelRegistry` + `ModelProviderBinding`.
  - Published retrieval pipeline (`VisualPipeline` + `ExecutablePipeline`).
  - Active knowledge store (Pinecone).
  - Platform SDK tool in `ToolRegistry`.
- Run the graph through `AgentExecutorService` in `DEBUG` and verify:
  - Final status is `completed`.
  - Expected node outputs and branch selections exist.
  - Approval flows complete and outputs map through end nodes.

**Scenarios Included**:
- **Support router**: Guardrail → classify → specialized agent → RAG + vector search → tool → approval → end
- **Query triage**: Rewrite → classify → if/else → RAG + vector search → tool → transform → end
- **Document compare**: Human input → if/else → agent → RAG + vector search → tool → approval → end

**Type**: Full‑stack integration tests (real DB + real services). These can be flaky when external services are down.

## Test Harness + Helpers
- **Builder helpers**: `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_builder_helpers.py`
- **Graph building** is declarative via helper functions; this mirrors the builder’s GraphSpec structure.

## Execution Behavior & Controls
- Tests run in **DEBUG** mode to surface event traces and intermediate outputs.
- Agents are created and (by default) **cleaned up**; to preserve agents for UI inspection, use:
  - `TEST_KEEP_AGENTS=1`
- Real DB is required for full‑stack tests:
  - `TEST_USE_REAL_DB=1`

## Gaps These Tests Expose
- **Frontend handle rendering** for classify/if_else: invalid handles break routing.
- **Missing node start/end events** for non‑agent nodes in debug stream.
- **Tool use inside agent nodes** depends on structured JSON output (not native tool binding).
- **RAG + vector search** as nodes work, but RAG as *agent tool* is not yet supported.

## Related Test State Files
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/agent_builder/test_state.md`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_execution_events/test_state.md`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_builder_large_agents/test_state.md`

These track last run commands, results, and known gaps.
