Last Updated: 2026-03-08

# Apps Builder E2B Runtime Migration Status

## Implemented Base

The app-builder draft-dev runtime now has a provider-abstracted sandbox layer under the existing `PublishedAppDraftDevRuntimeClient` contract.

Implemented pieces:
- `PublishedAppSandboxBackend` abstraction for session lifecycle, workspace/file operations, stage/publish flows, commands, and OpenCode calls
- backend adapters for:
  - `local`
  - `controller`
  - `e2b`
- backend selection through `APPS_SANDBOX_BACKEND` with `e2b` as the default when no controller override is configured
- draft-dev session persistence for:
  - `runtime_backend`
  - `backend_metadata`
- a platform-owned preview proxy at `/public/apps-builder/draft-dev/sessions/{session_id}/preview/...`
- preview auth bootstrap through the existing signed preview token, with cookie promotion for asset/HMR follow-up requests
- local dev runtime support for preview base paths so proxied Vite sessions work under the platform URL

## Current Shape

The public app-builder service contracts remain in place:
- `PublishedAppDraftDevRuntimeService`
- `PublishedAppDraftDevRuntimeClient`
- `OpenCodeServerClient` integration points
- existing publish/stage callers

What changed is the runtime substrate under those entrypoints:
- the old client transport branching is now delegated to backend adapters
- the E2B backend provisions sandboxes, syncs `/workspace`, reuses dependency markers, and starts preview/OpenCode processes inside the sandbox
- preview URLs returned to the frontend are now platform proxy URLs instead of raw sandbox hosts

## Immediate Follow-ups

Still needed before calling the migration complete:
- exercise the E2B backend against a real sandbox/template in an end-to-end environment
- add websocket-specific preview proxy coverage against live Vite HMR
- harden E2B reconnect/recovery paths for stale sandbox ids and orphaned processes
- wire operator-facing rollout controls per environment/tenant
- extend the same substrate to artifact runtime profiles after the app-builder path is proven

## Related Docs

- `backend/documentations/artifact_sandbox_architecture.md`
  - artifact-specific reuse plan on top of the same sandbox substrate
