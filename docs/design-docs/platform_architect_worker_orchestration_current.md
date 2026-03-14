# Platform Architect Worker Orchestration Current State

Last Updated: 2026-03-14

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
- `architect-worker-spawn`
- `architect-worker-spawn-group`
- `architect-worker-get-run`
- `architect-worker-join`
- `architect-worker-cancel`

These tools are the architect’s orchestration surface. The architect should not use raw `platform-governance` `orchestration.*` actions for worker delegation.

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
4. The architect later calls `architect-worker-get-run` or `architect-worker-join`.
5. The architect calls `architect-worker-binding-get-state`.
6. The architect persists the canonical payload through `platform-assets` (`artifacts.create` or `artifacts.update`).
7. The architect may optionally call `artifacts.create_test_run` and `artifacts.publish` subject to existing draft-first/publish-intent rules.

Important boundary:
- the worker edits only the shared draft
- canonical artifact persistence still happens through `platform-assets`

The backend now owns initial draft construction for the normal create path:
- the architect provides only the draft seed
- the backend generates the canonical initial snapshot from the artifact kind defaults
- the architect no longer needs to author files, contract blobs, or runtime defaults just to start the worker flow

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

## Strict Tool Contracts

Architect worker tools now run with strict pre-dispatch schema enforcement:
- model-authored payloads must match the registered input schema exactly
- nested wrapper recovery like `task.instructions`, `binding_payload`, `query`, or `value` is not part of the contract
- executor-owned runtime metadata is stripped before validation and passed separately through runtime context

Artifact binding exports now emit canonical platform-assets payloads:
- optional kind-specific contracts are omitted when unused instead of being returned as `null`
- this keeps `architect-worker-binding-get-state` output directly compatible with strict `platform-assets` mutation schemas

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
