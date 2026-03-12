# Platform Architect Artifact Delegation Current State

Last Updated: 2026-03-12

This document describes the current architect-specific artifact lifecycle and artifact-coding delegation model.

## Purpose

Platform Architect now treats artifact work as canonical revision-backed artifact CRUD plus optional delegation to the tenant-scoped `artifact-coding-agent`.

The goal is:
- no architect-facing legacy artifact draft/promote semantics
- one canonical artifact contract shared with the backend artifact APIs
- one shared session-backed draft substrate for direct artifact-page coding and architect-led coding

## Canonical Architect Artifact Surface

The architect artifact domain now uses these `platform-assets` actions:
- `artifacts.list`
- `artifacts.get`
- `artifacts.create`
- `artifacts.update`
- `artifacts.convert_kind`
- `artifacts.create_test_run`
- `artifacts.publish`
- `artifacts.delete`

Payloads are aligned to the canonical backend schemas in `backend/app/api/schemas/artifacts.py`.

Legacy architect-facing actions such as `artifacts.create_or_update_draft`, `register_asset`, and `create_artifact_draft` are removed.

## Delegation Toolset

Platform Architect now also receives three architect-only tools:
- `artifact-coding-session-prepare`
- `artifact-coding-session-get-state`
- `artifact-coding-agent-call`

These are seeded globally, but `artifact-coding-agent-call` targets the tenant-scoped published `artifact-coding-agent`.

## Delegation Flow

The architect delegation flow is:
1. Call `artifact-coding-session-prepare`.
2. Call `artifact-coding-agent-call` with the returned session context.
3. Call `artifact-coding-session-get-state`.
4. Persist the returned canonical artifact payload through `platform-assets`.
5. Optionally call `artifacts.create_test_run`.
6. Optionally call `artifacts.publish` only with explicit publish intent.

## Session Model

Delegation remains session-backed:
- child runs mutate only the shared draft snapshot
- child runs do not write canonical artifact rows directly
- create-mode stays keyed by `draft_key` until the architect persists the artifact
- after the first save, the architect re-prepares with `artifact_id` so the session/shared draft relinks to the canonical artifact

The same `ArtifactCodingRuntimeService` is shared by the artifact-coding router and the architect delegation tools.

## Guardrails

Current guardrails include:
- architect publish actions remain blocked unless explicit publish intent is provided
- child-agent execution still enforces tenant-scoped target resolution
- child-agent execution still requires a published target agent
