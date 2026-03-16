# Artifact Coding Agent Direct Use Current State

Last Updated: 2026-03-16

This document describes the current `artifact-coding-agent` runtime across the artifact page and architect worker delegation.

## Purpose

The artifact coding agent is now the canonical artifact authoring agent.

Current goals:
- edit the live artifact draft, including unsaved form state
- test draft changes against the canonical runtime when needed
- operate through one shared artifact session, draft, and chat-history substrate across the supported artifact-authoring surfaces

## Runtime Shape

The current implementation uses:
- a public seeded tenant agent profile: `artifact-coding-agent`
- artifact-scoped wrapper APIs under `/admin/artifacts/coding-agent/v1/*`
- shared runtime/session orchestration in `ArtifactCodingRuntimeService`
- persisted artifact coding sessions in `artifact_coding_sessions`
- persisted artifact coding chat messages in `artifact_coding_messages`
- shared `AgentExecutorService` runs and `AgentThread` threads behind the artifact-coding session runtime

Artifact coding runs are marked with:
- `AgentRun.surface = "artifact_coding_agent"`
- `AgentThread.surface = "artifact_admin"`

## Session Model

Each artifact coding chat session stores:
- tenant scope
- `scope_mode` fixed to `locked`
- optional saved `artifact_id`
- optional temporary `draft_key` for create mode
- backing shared `agent_thread_id`
- the current working draft snapshot using the full artifact page form shape
- active/last shared run ids
- last artifact test run id

The working draft snapshot is the mutation target for coding tools.
Canonical artifact rows and revisions are not mutated by tool calls.

Current scope model:
- `locked`
  - used by the artifact page and architect worker bindings
  - the session is bound to its current artifact/draft scope and cannot switch to another artifact from chat

## Tool Model

The artifact coding agent uses dedicated `FUNCTION` tools, not sandbox shell tools.

Current tool groups:
- context/read: form state, file listing, file reads, search
- mutation: file edits, metadata/runtime updates, kind/contract updates
- validation: run artifact test, fetch last test result

Mutation tools update only the shared working-draft snapshot for the current artifact scope and return:
- a short summary
- changed field names
- the normalized next draft snapshot

The frontend uses those tool results to update the live artifact editor state immediately.

Hard-cut scope rule:
- the agent only edits the current bound draft
- scope switching and persistence are owned by the caller surface, not by the agent

The same session/shared-draft runtime is reused by:
- the artifact page
- Platform Architect artifact-worker delegation

## Validation Path

`artifact_coding_run_test` snapshots the current session draft and calls the canonical artifact runtime through `ArtifactExecutionService.start_test_run(...)`.

This keeps authoring validation aligned with the real Cloudflare artifact execution path instead of a separate local coding sandbox.

Artifact persistence remains outside the coding agent:
- the artifact page Save flow persists
- Platform Architect persists through `architect-worker-binding-persist-artifact`
- the coding agent itself edits and validates the bound draft only

## Frontend Surface

The current frontend surfaces are:
- artifact page
  - right-side chat panel bound to the current artifact or create-mode draft
- architect worker mode
  - no separate UI, but the delegated worker uses the same artifact-coding session runtime underneath

Direct `artifact-coding-agent` use from the generic agent playground has been removed. The artifact chat UI remains intentionally separate from the app-builder coding UI so the artifact page can diverge later without affecting the app-builder surface.
