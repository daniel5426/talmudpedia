# Artifact Coding Agent Direct Use Current State

Last Updated: 2026-03-12

This document describes the current direct-use artifact coding agent surface on the admin artifact page.

## Purpose

The artifact coding agent provides a right-side chat authoring surface inside the artifact editor.

Current goals:
- edit the live artifact draft, including unsaved form state
- operate through the shared agent execution/thread/run substrate
- keep artifact draft persistence separate from explicit page Save and Publish
- validate behavior through the canonical artifact runtime test path

## Runtime Shape

The current implementation uses:
- a public seeded tenant agent profile: `artifact-coding-agent`
- shared `AgentExecutorService` runs and `AgentThread` threads
- artifact-scoped wrapper APIs under `/admin/artifacts/coding-agent/v1/*`
- shared runtime/session orchestration in `ArtifactCodingRuntimeService`
- persisted artifact coding sessions in `artifact_coding_sessions`
- persisted artifact coding chat messages in `artifact_coding_messages`

Artifact coding runs are marked with:
- `AgentRun.surface = "artifact_coding_agent"`
- `AgentThread.surface = "artifact_admin"`

## Session Model

Each artifact coding chat session stores:
- tenant scope
- optional saved `artifact_id`
- optional temporary `draft_key` for create mode
- backing shared `agent_thread_id`
- the current working draft snapshot using the full artifact page form shape
- active/last shared run ids
- last artifact test run id

The working draft snapshot is the mutation target for coding tools.
Canonical artifact rows and revisions are not mutated by tool calls.

## Tool Model

The artifact coding agent uses dedicated `FUNCTION` tools, not sandbox shell tools.

Current tool groups:
- context/read: form state, file listing, file reads, search
- mutation: file edits, metadata/runtime updates, kind/contract updates
- validation: run artifact test, fetch last test result

Mutation tools update only the session working snapshot and return:
- a short summary
- changed field names
- the normalized next draft snapshot

The frontend uses those tool results to update the live artifact editor state immediately.

The same session/shared-draft runtime is now also reused by Platform Architect delegation tools so architect-led artifact coding stays on the exact same draft substrate as direct artifact-page use.

## Validation Path

`artifact_coding_run_test` snapshots the current session draft and calls the canonical artifact runtime through `ArtifactExecutionService.start_test_run(...)`.

This keeps authoring validation aligned with the real Cloudflare artifact execution path instead of a separate local coding sandbox.

## Frontend Surface

The artifact page now includes:
- a copied app-builder-style right chat panel
- artifact-scoped services/hooks/components under `frontend-reshet/src/features/artifact-coding/`
- create-mode draft chat continuity through a persisted client `draft_key`

The artifact chat UI is intentionally not shared with the app-builder coding UI so the artifact page can diverge later without affecting the app-builder surface.
