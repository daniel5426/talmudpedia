# Platform Architect Worker Orchestration Current State

Last Updated: 2026-03-15

This document is the canonical design reference for the current `platform-architect` worker orchestration model.

## Purpose

The architect remains a single runtime agent, but delegated sub-work now runs through a dedicated async worker surface instead of the removed artifact-only synchronous wrapper.

The current goal is:
- keep canonical platform mutations on explicit domain APIs
- let the architect spawn async worker runs and inspect them later
- support durable, reversible worker state through bindings
- prove the model first with artifact coding

## Architect Worker Tool Surface

The architect now receives these dedicated tools:
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

These tools are the architect’s orchestration surface. The architect should not use raw `platform-governance` `orchestration.*` actions for worker delegation.

Current waiting contract:
- `architect-worker-get-run` is snapshot/debug only
- normal worker waiting should use `architect-worker-await`
- when a child blocks on input, the architect continues it with `architect-worker-respond`
- after a completed child run with no blocker, the normal persistence step is `architect-worker-binding-persist-artifact`

## Runtime Backbone

The new tool layer is built on top of the existing orchestration kernel:
- child run spawn
- parallel group spawn
- lineage
- group join
- subtree cancel
- policy and target allowlists

The architect-facing tools wrap that kernel with worker-specific contracts so the model does not have to author raw orchestration payloads.

## Binding Model

Bindings are typed references to durable worker state outside the LLM transcript.

V1 supports exactly one binding type:
- `artifact_shared_draft`

Normal create flow for this binding is now lightweight:
- `prepare_mode=create_new_draft`
- required: `title_prompt`, `draft_seed.kind`
- optional: `draft_seed.slug`, `draft_seed.display_name`, `draft_seed.description`, `draft_seed.entry_module_path`, `draft_seed.runtime_target`, `draft_key`, `replace_snapshot`

Advanced snapshot seeding still exists but is not the architect’s normal path:
- `prepare_mode=seed_snapshot`
- required: `title_prompt`, full canonical `draft_snapshot`

Binding responsibilities:
- prepare or reuse a shared draft/session
- attach canonical child-run context before spawn
- expose canonical export state later through `binding-get-state`
- preserve per-run draft snapshots/history on the existing artifact tables

Current binding guardrail:
- writable bindings are single-writer
- a second mutating worker on the same binding is rejected while the previous run is still active

## Artifact Worker Flow

Artifact coding is now implemented as one worker type under the generic architect worker runtime.

Current artifact flow:
1. `architect-worker-binding-prepare` creates or reuses the shared artifact draft session.
2. `architect-worker-spawn` or `architect-worker-spawn-group` launches async worker runs.
3. The spawned child run is bound to the artifact session via child context, including the artifact-coding surface marker.
4. The architect later waits through `architect-worker-await` or inspects through `architect-worker-get-run`.
5. The architect persists the binding server-side with `architect-worker-binding-persist-artifact`.
6. The architect may optionally call `architect-worker-binding-get-state` for inspection/debug/export.
7. The architect may optionally call `artifacts.create_test_run` and `artifacts.publish` subject to existing draft-first/publish-intent rules.

Important boundary:
- the worker edits only the shared draft
- canonical artifact persistence for worker-backed artifact drafts now happens inside the binding runtime, not through model-authored `platform-assets` passthrough

The backend now owns initial draft construction for the normal create path:
- the architect provides only the draft seed
- the backend generates the canonical initial snapshot from the artifact kind defaults
- the architect no longer needs to author files, contract blobs, or runtime defaults just to start the worker flow

Artifact session contract:
- `ArtifactCodingSession` now directly references its canonical shared draft through `shared_draft_id`
- artifact worker tools resolve draft state through that direct session link, not by re-deriving draft ownership from nullable scope
- architect child-run context now includes `artifact_coding_shared_draft_id` so worker resolution can fail fast on mismatched draft state

Current explicit contract rule:
- normal `create_new_draft` rejects full `draft_snapshot`
- advanced `seed_snapshot` accepts full canonical snapshots only
- guessed fields like `create`, `files`, `entrypoint`, and `text` now fail fast under strict validation

## Architect-Facing Shell Actions

The architect also now has lightweight first-create actions on the deterministic domain tools:
- `platform-agents` -> `agents.create_shell`
- `platform-rag` -> `rag.create_pipeline_shell`

These are intentionally orchestration-friendly:
- the architect provides a small intent/metadata payload
- the backend creates a minimal valid resource skeleton
- later mutations still use the canonical detailed mutation surfaces

Current limitation:
- `rag.create_pipeline_shell` currently supports retrieval shells only
- ingestion shells still require real source/storage/embedding configuration and are not auto-scaffolded in this refactor

## Async Semantics

`architect-worker-spawn` and `architect-worker-spawn-group` are async-only:
- they return immediately with run ids and lineage
- they do not wait for worker completion
- the architect decides when to inspect, join, or cancel later

Mutating architect worker tools now commit before returning durable identifiers or run metadata:
- `architect-worker-binding-prepare`
- `architect-worker-spawn`
- `architect-worker-spawn-group`
- `architect-worker-cancel`

This clean-cut commit rule exists because these tools run in separate DB sessions. A later tool call must be able to resolve the durable state created by an earlier one.

## Strict Tool Contracts

Architect worker tools now run with strict pre-dispatch schema enforcement:
- model-authored payloads must match the registered input schema exactly
- nested wrapper recovery like `task.instructions`, `binding_payload`, `query`, or `value` is not part of the contract
- executor-owned runtime metadata is stripped before validation and passed separately through runtime context

Artifact binding exports still emit canonical platform-assets payloads for inspection/debugging:
- optional kind-specific contracts are omitted when unused instead of being returned as `null`
- this keeps `architect-worker-binding-get-state` output directly compatible with strict `platform-assets` mutation schemas when export/inspection is needed, without any architect-side payload reshaping or `value` / `query` / `text` wrapping

## Strict Runtime Context

The worker tools derive caller identity from tool runtime context:
- `tenant_id`
- `initiator_user_id` / `user_id`
- `run_id`

Model-authored payloads do not own those fields.

## Removed Legacy Path

The old architect-only artifact delegation path is removed:
- `artifact-coding-session-prepare`
- `artifact-coding-agent-call`
- `artifact-coding-session-get-state`

There is no compatibility wrapper for that path in the live backend anymore.

## Current Validation Coverage

The current backend coverage for this model includes:
- worker tool seeding and architect prompt assertions
- async worker runtime unit coverage
- DB-backed seeded architect E2E for successful artifact worker flow
- DB-backed seeded architect E2E for active-binding rejection on a second mutating spawn
- optional/manual live architect smoke coverage for artifact-worker flow

## Current Known Gaps From Live Runs

The latest live runs exposed several root-cause gaps that are not yet resolved:

- The binding visibility bug between `prepare` and immediate `spawn` is fixed.
  - Root cause was transaction visibility across separate tool-call DB sessions.
  - The fix was to commit successful mutating architect worker tools before returning.

- The artifact worker delegated-mode gap is fixed.
  - The artifact coding agent profile now instructs delegated workers to complete `architect_worker_task` autonomously from the current shared draft.
  - When a delegated worker is genuinely blocked, it emits a final response beginning with `BLOCKING QUESTION:` so the orchestrator can detect the waiting state reliably.

- The session/shared-draft drift bug is fixed.
  - Root cause was indirect session-to-draft resolution through nullable `artifact_id` / `draft_key`.
  - The clean-cut fix adds a direct non-null `shared_draft_id` on `ArtifactCodingSession`, migrates existing rows, and makes worker resolution authoritative on that link.
  - Regression coverage now asserts that even scope-free architect-created sessions keep the same shared draft across later runtime resolution.

- Architect polling behavior is no longer based on tight `get-run` loops.
  - `architect-worker-await` now provides the normal server-side waiting primitive for child completion, failure, cancellation, or blocker detection.
  - The seeded architect prompt explicitly forbids repeated immediate `architect-worker-get-run` polling and directs waiting children through `architect-worker-respond`.

- The large-object pass-through persistence problem is fixed for the worker-backed artifact path.
  - Root cause was structural: the architect had to restate a large exported `platform_assets_create_input` or `platform_assets_update_input` object from prior tool output into a new strict `platform-assets` call.
  - That forwarding step degraded into model-authored `value: "<json string>"` wrappers even after executor hardening.
  - The clean-cut fix is `architect-worker-binding-persist-artifact`, which persists the binding-backed draft server-side through `ArtifactRevisionService` and links the session/shared-draft scope to the canonical artifact after create.
  - `architect-worker-binding-get-state` remains available for export/inspection, but it is no longer the normal persistence bridge.

- Artifact seed vocabulary is still not natural enough for the architect.
  - The architect still guesses values like `python` or `script` instead of the canonical artifact kinds (`tool_impl`, `agent_node`, `rag_operator`).
