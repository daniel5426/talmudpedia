# Agent Execution Current State

Last Updated: 2026-03-12

This document describes the current agent execution architecture as implemented in the backend.

## Core Model

Agent execution uses a unified execution service with graph compilation, streaming events, run persistence, and trace recording.

Primary implementation points:
- `backend/app/agent/execution/service.py`
- `backend/app/agent/graph/compiler.py`
- `backend/app/agent/runtime/`
- `backend/app/agent/execution/trace_recorder.py`
- `backend/app/api/routers/agent.py`
- `backend/app/api/routers/agents.py`
- `backend/app/api/routers/agent_run_logs.py`

## What Is Stable In The Current Code

- A graph definition is compiled before execution.
- Runs are persisted as `AgentRun` records.
- Thread resolution is part of run startup.
- Usage quota reservation happens before execution for most surfaces.
- Execution emits structured events and records traces.
- Runtime behavior can vary by execution mode and calling surface without requiring separate engines.

## Execution Responsibilities

### Run Startup

`AgentExecutorService.start_run()` is responsible for:
- loading the target agent
- resolving runtime context
- resolving or creating the thread
- reserving quota where applicable
- creating the run record
- preparing the execution context for downstream runtime execution

This is not just “kick off a LangGraph.” It is the orchestration boundary where identity, thread ownership, quota, and runtime context are normalized.

### Graph Execution

Execution is based on compiled graph definitions and runtime adapters.

Current execution architecture includes:
- compiler-driven validation and executable preparation
- runtime adapter registry
- durable checkpoint support
- event emission with typed execution events
- trace recording through a shared recorder

### Streaming and Visibility

The system supports divergent observability by execution mode and surface. The exact frontend contract can vary, but the backend architecture clearly separates:
- internal/high-fidelity execution data
- client-safe streamed output

That separation appears in event types, stream contracts, trace recording, and surface-specific routers.

Current stream-contract rule:
- generic runtime `error` events are non-terminal diagnostics
- only explicit terminal run events such as `run.completed`, `run.failed`, `run.cancelled`, and `run.paused` should terminate client streaming flows
- persisted run traces can be replayed by `run_id` through `GET /agents/runs/{run_id}/events`, which is now the canonical path for thread-history trace rehydration

### Node Execution

The node execution layer is broader than a simple LLM-and-tools loop. The current executor set includes:
- logic executors
- tool executors
- artifact executors
- retrieval/RAG executors
- orchestration executors
- interaction and classification executors

This confirms the agent runtime is a graph runtime for heterogeneous node types, not just a chat wrapper.

Current artifact-specific behavior:
- tenant artifact nodes execute through the shared artifact runtime
- production runs pin tenant artifact nodes to published artifact revisions during graph compile/startup
- live tenant artifact node execution now uses the Cloudflare-backed artifact runtime path
- that pinning is currently per run, not yet a full immutable published-agent snapshot

## Current Integrations

Agent execution integrates with:
- workload delegation and workload identity
- thread service and thread ownership checks
- usage quota reservation and settlement
- published app contexts
- model resolution and tool registries
- trace and event persistence

## Current Architectural Constraints

- Execution context must remain tenant-scoped and identity-aware.
- Public or external-facing surfaces should not receive internal-only execution detail.
- Quota and policy enforcement must happen outside the hot token-stream path where possible.
- Thread ownership and resume behavior must remain explicit and validated.
- Trace recording should remain reusable across runtimes, not embedded as ad-hoc debug logging.

## Relationship To Older Docs

This document replaces simplified descriptions that only emphasize:
- debug vs production streaming
- a single stream adapter concept
- an advanced-rag-first execution story

Those ideas still matter, but the live system now includes more runtime concerns: thread resolution, quota enforcement, workload delegation, richer node executors, and multiple runtime surfaces.
