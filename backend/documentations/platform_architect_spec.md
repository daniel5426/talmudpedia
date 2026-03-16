# Platform Architect Spec

Last Updated: 2026-03-16

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
- `architect-worker-binding-persist-artifact`
- `architect-worker-spawn`
- `architect-worker-spawn-group`
- `architect-worker-get-run`
- `architect-worker-await`
- `architect-worker-respond`
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
5. Wait for child progress with `architect-worker-await`, use `architect-worker-get-run` only for inspection/debugging, and answer waiting children with `architect-worker-respond` when needed.
6. Persist worker-backed artifact drafts through the dedicated binding persist tool; use explicit platform APIs for other domain mutations.
7. Return a normal text response.

Current observability note:
- `architect-worker-respond` emits reusable execution-trace events on the architect run and the relevant worker run, including whether it chose native resume or native conversation continuation and which worker thread ids were involved.

Current continuation contract:
- `architect-worker-respond` is no longer limited to waiting children; it may also continue a completed worker conversation on the same binding/session/thread context when the architect wants additional edits from the same worker.
- For binding-backed conversational workers, the binding/runtime prepares native session-history input and the orchestration kernel creates the continued child run with normal architect lineage.

Important prompt boundary:
- raw `orchestration.spawn_*` actions are not part of the architect-visible `platform-governance` contract
- use the dedicated architect worker tools for worker delegation

## Domain Tool Boundaries
- `platform-rag` -> `rag.*`
- `platform-agents` -> `agents.*`
- `platform-assets` -> `artifacts.*`, `tools.*`, `models.*`, `credentials.*`, `knowledge_stores.*`
- `platform-governance` -> `auth.*`, `workload_security.*`, `orchestration.join`, `orchestration.cancel_subtree`, `orchestration.evaluate_and_replan`, `orchestration.query_tree`

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
- persist a binding-backed artifact server-side
- spawn one worker asynchronously
- spawn a parallel worker group asynchronously
- inspect a child run later
- await child completion/blocking server-side
- respond to a waiting child run
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

Mutating architect worker tools now commit before returning:
- `architect-worker-binding-prepare`
- `architect-worker-spawn`
- `architect-worker-spawn-group`
- `architect-worker-cancel`

This is required because each tool function runs in its own DB session and later tool calls must be able to re-read the durable state created by earlier ones.

## Binding Model

Bindings are typed references to durable worker state outside the transcript.

Current supported binding type:
- `artifact_shared_draft`

Artifact binding behavior:
- prepare or reuse an artifact shared draft/session
- bind child artifact-coding runs to that session
- preserve run-linked snapshots/history on the existing artifact tables
- later export canonical artifact create/update payloads for inspection/debugging
- persist the current draft server-side through `ArtifactRevisionService`
- artifact-coding sessions now hold a direct non-null `shared_draft_id` so worker tools resolve the prepared draft by identity, not by nullable scope inference
- binding state now exposes `persistence_readiness` so create-mode drafts with missing required metadata do not attempt canonical persistence blindly
- binding/session state now also exposes `verification_state` so latest artifact test-run outcome is not conflated with structural persistence readiness

Normal artifact binding creation is now lightweight:
- `prepare_mode=create_new_draft`
- required: `title_prompt`, `draft_seed.kind`
- optional seed metadata: `display_name`, `description`, `entry_module_path`, `runtime_target`

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
3. `architect-worker-await` for the normal waiting path
4. if more edits are needed from the same worker, `architect-worker-respond`
5. `architect-worker-await` on the latest continued child
6. `architect-worker-binding-persist-artifact`
7. optional `architect-worker-binding-get-state` for inspection/debug/export
8. optional `artifacts.create_test_run`
9. optional `artifacts.publish` only with explicit publish intent

Important ownership boundary:
- the child worker edits only the shared draft
- architect-owned binding persistence remains available through `architect-worker-binding-persist-artifact`

The architect should not author full `draft_snapshot` payloads for normal artifact creation.
The backend now creates the canonical initial draft snapshot from the supplied `draft_seed`.

Continuation contract for artifact workers:
- paused child needing input -> native run resume
- completed child needing more edits -> append an `orchestrator` turn to the existing artifact coding session, prepare the next run from true stored history, and let the orchestration kernel create the continued child run inside the architect tree
- initial architect spawn also uses the artifact session's native `agent_thread_id`, so spawn and continuation share the same worker conversation thread
- `orchestrator` turns remain visible in chat history and are not treated as user-authored turns
- when the worker validates code through the artifact test runtime, the normal contract is `artifact-coding-run-test` once, then `artifact-coding-await-last-test-result`; repeated restart loops on queued Cloudflare test runs are no longer valid behavior
- architect worker sessions use locked artifact-coding scope and cannot switch to another artifact from chat

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

## Current Live-Run Gaps

Recent live runs isolated the next unresolved problems:

- The old `prepare -> spawn` binding-not-found failure is fixed.
  - Root cause was missing commits between separate mutating architect worker tool calls.

- The delegated artifact worker mode is now explicit, but live behavior is still inconsistent.
  - The artifact coding agent profile instructs architect-spawned workers to complete `architect_worker_task` autonomously, persist their own draft when the task requires save/create/update, and avoid user-facing scope switching in locked sessions.
  - Some live runs still show the worker behaving like a chatty editor instead of executing the delegated task directly.

- Session-to-shared-draft resolution for fresh architect-created bindings is structurally weak.
  - Fixed by adding `ArtifactCodingSession.shared_draft_id` and migrating existing sessions onto canonical shared drafts.
  - Worker resolution is now direct and child-run context includes `artifact_coding_shared_draft_id` for mismatch detection.
  - Regression coverage now asserts that scope-free architect-created sessions do not create or resolve a second shared draft later.

- Architect waiting no longer relies on repeated `architect-worker-get-run` loops.
  - `architect-worker-await` is now the normal waiting primitive for completion, failure, cancellation, or blocker detection.
  - `architect-worker-respond` provides the pull-model continuation path for child runs that are waiting for orchestrator input.

- The worker-backed artifact persistence pass-through failure is fixed.
  - Root cause was the architect having to restate a large exported `platform_assets_create_input` / `platform_assets_update_input` object into a new strict `platform-assets` call.
  - The clean-cut fix is `architect-worker-binding-persist-artifact`, which reads canonical binding state server-side, chooses create vs update, persists through `ArtifactRevisionService`, and links the binding/session/shared-draft scope to the canonical artifact after create.
  - `architect-worker-binding-get-state` remains available for inspection/debugging, but it is no longer the normal persistence bridge.

- Session-native continuation no longer escapes architect lineage.
  - Root cause was direct runtime-owned run creation during continuation, which produced real worker history but lost `root_run_id` / `parent_run_id`.
  - The clean-cut fix keeps native session-history preparation in the binding/runtime layer while routing final child-run creation back through the orchestration kernel.
  - Continued worker runs are now awaitable, cancellable, and joinable from the same architect run tree.

- Create-mode persistence now rejects obviously unready drafts.
  - Missing required metadata like empty `display_name` is exposed through `persistence_readiness`.
  - The architect should continue the worker or return a blocker instead of attempting canonical create on an unready draft.

- Artifact draft seed ergonomics are still rough for the architect.
  - The architect continues to guess non-canonical values like `python` or `script` instead of artifact-domain kinds like `tool_impl`.
