# Platform Architect Spec

Last Updated: 2026-03-14

## Purpose
This file is the focused current-state reference for the seeded `platform-architect` runtime.

## Current Runtime
- Active runtime is still a single `platform-architect` agent.
- It is a tool-using backend runtime, not the removed staged GraphSpec orchestrator.
- The architect can now supervise async worker runs through dedicated architect worker tools.

## Seeded Tool Surface

The architect is seeded with:
- `platform-rag`
- `platform-agents`
- `platform-assets`
- `platform-governance`
- `architect-worker-binding-prepare`
- `architect-worker-binding-get-state`
- `architect-worker-spawn`
- `architect-worker-spawn-group`
- `architect-worker-get-run`
- `architect-worker-join`
- `architect-worker-cancel`

Primary implementation files:
- `backend/app/services/registry_seeding.py`
- `backend/app/services/platform_architect_contracts.py`
- `backend/app/services/platform_architect_worker_tools.py`
- `backend/app/services/platform_architect_worker_runtime_service.py`
- `backend/app/services/platform_architect_worker_bindings.py`

## Architect Behavior

The architect runtime should:
1. Extract intent and constraints.
2. Decide whether work is local deterministic platform work or delegated worker work.
3. Use direct domain tools for canonical platform reads/mutations.
4. Use architect worker tools for async delegated work, especially longer-running or mutable draft work.
5. Poll or join child runs later when needed.
6. Persist canonical results through explicit platform APIs.
7. Return a normal text response.

Important prompt boundary:
- do not use raw `platform-governance` `orchestration.*` actions for worker delegation
- use the dedicated architect worker tools instead

## Domain Tool Boundaries
- `platform-rag` -> `rag.*`
- `platform-agents` -> `agents.*`
- `platform-assets` -> `artifacts.*`, `tools.*`, `models.*`, `credentials.*`, `knowledge_stores.*`
- `platform-governance` -> `auth.*`, `workload_security.*`, `orchestration.*`

Cross-domain action usage through the wrong domain tool is denied with `SCOPE_DENIED`.

Preferred first-create actions:
- `platform-agents` -> `agents.create_shell`
- `platform-rag` -> `rag.create_pipeline_shell`

The architect should prefer these shell actions for first creation instead of constructing full agent graphs or RAG node/edge payloads up front.
Current limit: `rag.create_pipeline_shell` is retrieval-only in this refactor.

## Worker Orchestration Model

The architect worker runtime is async and kernel-backed.

Current architect worker capabilities:
- prepare a binding-backed worker state
- spawn one worker asynchronously
- spawn a parallel worker group asynchronously
- inspect a child run later
- join a worker group later
- cancel a worker subtree

The orchestration kernel remains the execution backbone for:
- child run spawn
- group spawn
- lineage
- join
- cancel
- policy checks and target allowlists

The architect does not author raw kernel payloads directly.

## Binding Model

Bindings are typed references to durable worker state outside the transcript.

Current supported binding type:
- `artifact_shared_draft`

Artifact binding behavior:
- prepare or reuse an artifact shared draft/session
- bind child artifact-coding runs to that session
- preserve run-linked snapshots/history on the existing artifact tables
- later export canonical artifact create/update payloads

Normal artifact binding creation is now lightweight:
- `prepare_mode=create_new_draft`
- required: `title_prompt`, `draft_seed.kind`
- optional seed metadata: `slug`, `display_name`, `description`, `entry_module_path`, `runtime_target`

Advanced full snapshot seeding still exists:
- `prepare_mode=seed_snapshot`
- requires `title_prompt` plus a full canonical `draft_snapshot`

Writable bindings are single-writer:
- one active mutating worker per binding
- a second mutating spawn on the same binding is rejected with `BINDING_RUN_ACTIVE`

## Artifact Worker Flow

Current architect artifact flow:
1. `architect-worker-binding-prepare`
2. `architect-worker-spawn` or `architect-worker-spawn-group`
3. `architect-worker-get-run` or `architect-worker-join`
4. `architect-worker-binding-get-state`
5. `platform-assets` `artifacts.create` or `artifacts.update`
6. optional `artifacts.create_test_run`
7. optional `artifacts.publish` only with explicit publish intent

Important ownership boundary:
- the child worker edits only the shared draft
- the architect still performs canonical artifact persistence through `platform-assets`

The architect should not author full `draft_snapshot` payloads for normal artifact creation.
The backend now creates the canonical initial draft snapshot from the supplied `draft_seed`.

## Removed Legacy Path

The old architect-only artifact delegation path is removed:
- `artifact-coding-session-prepare`
- `artifact-coding-session-get-state`
- `artifact-coding-agent-call`

There is no compatibility wrapper for that path in the live architect runtime.

## Safety and Mutation Rules
- Architect runtime remains tenant-bound.
- Runtime tenant context is authoritative for mutations.
- Architect should not ask the user for `tenant_id`.
- Publish actions remain blocked unless explicit publish intent is present.
- Approval-sensitive failures continue to normalize through the existing Platform SDK error contract.
- Wrapped `value` / `query` / `text` recovery is not part of the platform SDK path; canonical top-level `action` / `payload` is required there.
- Architect worker tools derive `tenant_id`, user identity, and `run_id` from runtime context, not from model-authored payload.
- Strict platform tools are validated before function dispatch against their registered JSON-schema input contract.
- Executor-owned runtime metadata is removed from strict tool payload validation and passed separately in `__tool_runtime_context__`.
- Canonical artifact create/update payloads exported from worker bindings omit unused optional contracts instead of emitting `null`.
- Architect-facing worker binding creation now explicitly rejects low-level guessed fields like `create`, `files`, `entrypoint`, and `text`.

## Active Test Coverage

Focused architect worker coverage now lives in:
- `backend/tests/platform_architect_workers/`

Current coverage includes:
- worker tool seeding assertions
- architect prompt/tool-surface assertions
- async spawn-group validation
- child-run binding metadata inspection
- DB-backed seeded architect run that spawns an artifact worker and persists the artifact successfully
- DB-backed seeded architect run that rejects a second mutating spawn on an active binding

Live E2E coverage remains in:
- `backend/tests/platform_architect_e2e/`

An optional/manual live smoke path now exists for architect artifact-worker flow.
