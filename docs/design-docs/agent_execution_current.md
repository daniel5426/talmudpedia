# Agent Execution Current State

Last Updated: 2026-04-21

This document describes the current agent execution architecture as implemented in the backend.

## Core Model

Agent execution uses a unified execution service with graph compilation, streaming events, run persistence, and trace recording.

Primary implementation points:
- `backend/app/agent/execution/service.py`
- `backend/app/agent/graph/compiler.py`
- `backend/app/agent/runtime/`
- `backend/app/agent/execution/trace_recorder.py`
- `backend/app/api/routers/agents.py`
- `backend/app/api/routers/agent_run_logs.py`

Legacy note:
- the old legacy `/chat` bootstrap route and the old `advanced_rag` / `simple_rag` workflow files were hard-removed on 2026-03-20
- maintained execution paths now flow through the graph compiler, runtime adapter, model resolver, and executor stack listed above

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

Current nested-run rule:
- synchronous `agent_call` child runs execute inside a dedicated fresh `AsyncSession`
- synchronous `agent_call` child runs also execute inside a dedicated child task, and cancellation drains that task before the child session closes
- the parent tool/node session no longer owns child run creation or child run streaming
- cancelled parent runs are not allowed to spawn new child runs through `agent_call` or orchestration fanout paths

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
- persisted run traces now also support incremental replay via `after_sequence` and `limit`
- tool lifecycle events now separate identity from attribution: `span_id` is the unique tool-call span and `source_node_id` identifies the owning graph node
- `POST /agents/runs/{run_id}/cancel` now cancels the full descendant run subtree rooted at that run, not just the selected root row
- subtree cancel now also cancels any live in-process run task registered for those run ids, so abort can interrupt an active nested `agent_call` wait instead of only flipping DB state
- subtree cancel now also marks the full live run subtree in a shared in-process cancellation registry keyed by run/root lineage, and nested execution checks that registry before node dispatch, tool execution, orchestration fanout, and child `start_run`
- a run already marked `cancelled` must not be revived back to `running` if its worker starts late
- runtime-stream cancellation now cancels the underlying LangGraph task instead of waiting for it to keep running in the background, which is required for abort and timeout to stop nested delegated runs cleanly
- generic `/agents/{id}/stream` is now a detached read-side stream over persisted run events; disconnecting the client no longer cancels the underlying run
- the cancel endpoint no longer writes thread turns synchronously; turn finalization stays with the run worker to avoid deadlocks on `agent_threads`
- reasoning nodes now recheck current run cancellation at tool-loop boundaries, so a cancelled run stops after the active tool returns instead of continuing into another post-tool model iteration
- cancellation-sensitive run-state checks now use direct SQL refreshes instead of session-cached `AgentRun` reads, and `ToolNodeExecutor` rechecks the current run immediately before nested `agent_call` child creation
- runtime cancellation markers now persist for the life of the process for that run subtree instead of being cleared when a single run task exits, which prevents later descendant spawns from an already-cancelled root
- cancellation now performs best-effort session rollback before a cancelled execution frame unwinds, so task cancellation does not close request-scoped or child-owned SQLAlchemy sessions in an illegal transaction state

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
- tenant API-key authenticated embedded-agent runtime
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

## Runtime Surface Split

The current execution core is shared, but the public contracts are intentionally separate:
- `/agents/{id}/stream` remains the internal/control-plane execution route
- published apps keep their app-scoped runtime surfaces
- embedded-agent runtime uses `/public/embed/agents/{agent_id}/*` with tenant API keys and `external_user_id` thread ownership

So the runtime engine is unified below the route/auth layer, while product contracts remain surface-specific.

## Runtime Surface Facade

Runtime-surface orchestration is now standardized through a shared internal facade in `backend/app/services/runtime_surface/`.

- `AgentExecutorService` remains the execution engine and still owns run creation, thread resolution, quota checks, and graph execution.
- The runtime-surface facade now owns shared route-side behavior: start/resume request normalization, prior-thread preload where applicable, persisted stream response assembly, internal run-event fetch, internal cancel handling, and shared public thread-detail serialization helpers.
- Internal, published, and embedded routes still preserve different auth, ownership, and visibility contracts; they now act as thin adapters over the same lifecycle/query layer.
- Public-safe historical run events are generated from one shared path instead of separate embed and published implementations.
- Published host runtime and builder preview thread list/detail flows now call the canonical runtime-surface lifecycle/query service directly rather than routing through serializer compatibility wrappers.
- The old foreground disconnect cancel helper path is intentionally gone; canonical cancellation is the run-control route plus subtree cancellation in the orchestration kernel.

## Worker-Owned Generic Runs

Generic top-level background execution is now worker-owned.

- `AgentExecutorService.start_run(..., background=True)` queues the run instead of starting in-process execution.
- generic background runs are dispatched to Celery on the `agent_runs` queue
- `agent_runs` persists execution-ownership metadata such as dispatch count, lease expiry, heartbeat, and worker owner id
- worker claim logic prevents duplicate execution when a live lease exists
- lease expiry allows recovery when a worker dies before terminal completion
- synchronous nested child runs still execute inline inside the owning worker process; only explicitly background runs are detached again

## Detached Foreground Streaming

Foreground stream routes no longer own execution.

- `/agents/{id}/stream`
- published-app generic chat streams
- embedded-agent generic chat streams

These routes now:
- create or resume a run in worker-owned background execution
- attach to persisted run events
- replay history on reconnect
- close when persisted status reaches a terminal state

This means stream transport lifetime is now decoupled from run lifetime for generic detached flows.

Current platform-architect startup rule:
- the seeded `platform-architect` agent requires `context.architect_mode` on new `/agents/{id}/stream` runs
- internal playground/builder callers should send an explicit mode such as `default`; this is no longer inferred server-side
- missing `context.architect_mode` fails run startup with HTTP 400 before graph execution begins

## Relationship To Older Docs

This document replaces simplified descriptions that only emphasize:
- debug vs production streaming
- a single stream adapter concept
- an advanced-rag-first execution story

Those ideas still matter, but the live system now includes more runtime concerns: thread resolution, quota enforcement, workload delegation, richer node executors, and multiple runtime surfaces.
