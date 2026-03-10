# Apps Builder Current Implementation Overview

Last Updated: 2026-03-10

## Purpose
This document is the current-state overview of the Apps Builder system (not a future implementation plan). It summarizes how the builder works today across backend, frontend, runtime, coding-agent, revision persistence, and publish/runtime delivery.

## Product-Level Model
Apps Builder currently operates in two execution modes:
- Draft mode (builder editing + preview): optimized for speed and iteration.
- Publish mode (immutable runtime artifact): optimized for determinism and stability.

Core implementation choices in current state:
- Draft preview uses one persistent shared Sprite workspace per app with per-user attachment sessions.
- Draft preview is now driven by a long-lived Vite build watcher plus static preview serving, not `vite dev`.
- Coding-agent runs write directly into the canonical shared workspace; stage/live promotion is removed.
- Published runtime remains static artifact delivery (`vite_static`).
- Draft revisions created from preview builds are already materialized with dist artifacts; app-builder draft revision build jobs are no longer the primary path.

## Credential Handling in Builder Runtime
- Builder-generated apps and coding-agent runs do not embed provider API keys in template files.
- Runtime credential resolution follows the platform-wide Integration Credential chain:
  1. Explicit `credentials_ref` on the bound model/tool/store.
  2. Tenant default provider credential.
  3. Platform default provider env var fallback.
- This allows zero-config out-of-box behavior for standard providers while preserving tenant override capability from Settings.

## High-Level Architecture
### Backend Core Areas
- API routers for builder/admin/public runtime:
  - `backend/app/api/routers/published_apps_admin.py`
  - `backend/app/api/routers/published_apps_admin_routes_apps.py`
  - `backend/app/api/routers/published_apps_admin_routes_builder.py`
  - `backend/app/api/routers/published_apps_admin_routes_coding_agent.py`
  - `backend/app/api/routers/published_apps_public.py`
- Draft-dev runtime management:
  - `backend/app/services/published_app_draft_dev_runtime.py`
  - `backend/app/services/published_app_draft_dev_runtime_client.py`
  - `backend/app/services/published_app_draft_dev_local_runtime.py`
- Coding-agent orchestration:
  - `backend/app/services/published_app_coding_agent_runtime.py`
  - `backend/app/services/published_app_coding_agent_engines/opencode_engine.py`
  - `backend/app/services/opencode_server_client.py`
- Revisions/templates/storage:
  - `backend/app/services/published_app_revision_store.py`
  - `backend/app/services/published_app_templates.py`
  - `backend/app/services/published_app_bundle_storage.py`
- Shared lifecycle tracing:
  - `backend/app/services/apps_builder_trace.py`
  - `backend/app/services/published_app_coding_pipeline_trace.py`

### Frontend Core Areas
- Builder workspace shell:
  - `frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx`
- Builder coding-agent chat orchestration:
  - `frontend-reshet/src/features/apps-builder/workspace/chat/useAppsBuilderChat.ts`
  - `frontend-reshet/src/features/apps-builder/workspace/chat/AppsBuilderChatPanel.tsx`
- Service contracts:
  - `frontend-reshet/src/services/published-apps.ts`

## Template System
Template packs are filesystem-backed and loaded from:
- `backend/app/templates/published_apps/*`

Current template catalog includes:
- `chat-classic`, `chat-grid`, `chat-editorial`, `chat-neon`, `chat-soft`, `fresh-start`

Behavior today:
- Builder create/reset uses template manifests + file maps.
- Canonical runtime/common + OpenCode bootstrap overlays are injected into all templates:
  - `src/runtime-sdk.ts` wrapper
  - `src/runtime-config.json` app-context payload
  - `runtime-sdk/*` package payload (`@talmudpedia/runtime-sdk`)
  - `.opencode/package.json`
  - `.opencode/tools/read_agent_context.ts`
- OpenCode run startup also self-heals these bootstrap files for legacy drafts.
- Canonical runtime bootstrap overlay is also re-applied during draft-dev session materialization and publish build materialization to prevent stale runtime SDK contracts.

## Draft Preview Runtime
Draft preview uses Sprite-backed shared workspaces with one canonical source tree plus preview-build snapshots.

Session lifecycle APIs:
- `GET /admin/apps/{app_id}/builder/draft-dev/session`
- `POST /admin/apps/{app_id}/builder/draft-dev/session/ensure`
- `PATCH /admin/apps/{app_id}/builder/draft-dev/session/sync`
- `POST /admin/apps/{app_id}/builder/draft-dev/session/heartbeat`
- `DELETE /admin/apps/{app_id}/builder/draft-dev/session`

Important runtime behavior:
- One shared Sprite is owned at app scope; user sessions attach to it.
- Persistent filesystem means dependencies are reused across re-entry and provider warm/cold transitions.
- The visible iframe is served from the latest successful preview build snapshot, not live source modules.
- Preview build failures do not blank the iframe; the last successful snapshot remains served while error metadata is exposed in draft-dev session payloads.
- Builder state reloads now heartbeat the active draft session before responding, so post-run UI refreshes pick up the newest preview-build metadata immediately instead of waiting for the background heartbeat interval.
- Builder preview iframe URL stays stable and tokenless across heartbeat/token refresh.
- Draft-dev session response carries off-URL auth fields (`preview_auth_token`, `preview_auth_expires_at`) plus preview-build metadata (`preview_build_status`, `preview_build_error`, `preview_build_seq`, `current_preview_build_id`, `current_preview_built_at`).
- Version preview inspection follows the same off-URL token rule: the selected-version preview URL is tokenless and the admin response carries the runtime token separately, so iframe reloads cannot mix a new revision URL with an old revision token.
- Public preview auth now prefers an explicit `runtime_token` query param over any preview cookie so switching between inspected revisions cannot be pinned to a stale cookie token.
- Historical version preview rewrites root-relative built asset URLs (`/assets/...`) onto the revision-scoped preview asset path so saved Vite bundles render correctly outside the draft preview root.
- For Vite dist outputs, revision preview keeps the original `assets/...` segment when rewriting, because the stored bundle keys are rooted at `dist/assets/*`, so the correct public path shape is `/public/apps/preview/revisions/{id}/assets/assets/*`.
- Public revision-preview auth uses its own cookie channel (`published_app_public_preview_token`) so inspected version assets cannot accidentally inherit the draft-preview session token.
- Draft-dev preview URLs are decorated only with runtime routing query params so template runtime clients can resolve chat base path in preview:
  - `runtime_mode=builder-preview`
  - `runtime_base_path={resolved_runtime_api_base}/public/apps/preview/revisions/{revision_id}`
- Builder sends preview auth to iframe runtime via `window.postMessage` (`talmudpedia.preview-auth.v1`), and runtime SDK uses bearer auth headers for preview chat stream calls.
- Draft-dev sandbox, preview proxy, coding-agent, and publish flows now emit shared structured lifecycle events to the app-builder trace stream for operational debugging.

## Coding-Agent Runtime (Current)
### Shared Sprite, Single-Workspace Model
Coding-agent execution now targets the same canonical shared workspace that the preview builder watches.

Run flow:
1. Submit prompt (`POST /coding-agent/v2/prompts`) and resolve active preview sandbox session.
2. Start OpenCode against the canonical workspace path.
3. Stream run events to frontend (assistant/tool/terminal events).
4. When a run terminalizes, mark it as waiting for the next successful preview build.
5. The first successful preview build after terminalization materializes a draft revision from the exact preview-build snapshot and assigns that revision to all waiting completed runs it satisfies.

Revisioning behavior:
- No stage/live promotion or batch finalizer remains.
- Overlapping completed runs may resolve to one combined auto-created revision if they are both waiting when the same successful preview build lands.

### Streaming and Stall Ownership (Current Defaults)
- Backend monitor owns forced terminalization policies; aggressive fail-close is env-gated.
- Runtime stream missing-terminal behavior is non-fatal by default (reconcile-first, no runtime force-fail toggle).
- Monitor inactivity/EOF fail-close paths are disabled by default and can be enabled via:
  - `APPS_CODING_AGENT_MONITOR_FORCE_TERMINAL_ON_INACTIVITY`
  - `APPS_CODING_AGENT_MONITOR_FORCE_TERMINAL_ON_STREAM_END_WITHOUT_TERMINAL`
- Frontend stream stall handler is non-destructive by default:
  - does not auto-cancel stalled runs unless `NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_AUTO_CANCEL_RECOVERY_ENABLED=1`
  - reconciles terminal state from backend first when stream ends without terminal event

### Locking and Idempotency
- Builder writes are blocked while active coding run count for scope is `> 0` (`CODING_AGENT_RUN_ACTIVE`).
- Active-run lock source-of-truth is `agent_runs` non-terminal count, not draft-dev pointer columns.
- Run create accepts `client_message_id` for idempotent submission.

### Chat/History
- Chat sessions and chat messages are persisted server-side.
- Frontend can resume chat sessions and reuse `chat_session_id` across runs.
- Run tool events are now persisted in run output payload (`output_result.tool_events`) and returned via chat-session detail `run_events` so reload can reconstruct tool-call timeline rows.
- Build-related publish failures can now trigger a best-effort auto-fix coding-agent prompt in the latest existing chat session for the publishing user.

## OpenCode Integration
OpenCode is the default engine path in current state.

Current integration model:
- No OpenCode MCP contract registration path.
- Project-local custom tool bootstrap (`.opencode/*`) is seeded per run if needed.
- `read_agent_context` is the consolidated custom tool for selected-agent context reads.
- Run startup fails closed when required bootstrap/context seeding fails.
- Sprite-backed OpenCode traffic is routed through a backend-owned Sprite proxy tunnel to the in-Sprite `127.0.0.1:4141` service, not through public `https://<sprite>.sprites.app:4141` access.
- Tool event passthrough defaults to raw OpenCode semantics (`APPS_CODING_AGENT_OPENCODE_TOOL_EVENT_MODE=raw`), with optional normalized mapping mode for legacy UI behavior.
- Wrapper apply-patch unrecovered fail-close is opt-in (`APPS_CODING_AGENT_OPENCODE_FAIL_ON_UNRECOVERED_APPLY_PATCH=0` by default).

Recent stability hardening reflected in code/docs:
- Improved terminal event handling to reduce hanging runs.
- Stream handling tuned for incremental assistant deltas.
- Cancel path supports sandbox-routed cancellation and run finalization semantics.
- Idle-batch finalization with advisory lock per `app_id` to prevent duplicate promotions/revisions during parallel completion races.

## Revision Persistence Model
Current revision persistence uses snapshot-manifest + content-addressed blob storage.

Core behavior:
- Manifest maps `path -> blob_hash`.
- Blobs are stored under revision-blob prefix in object storage.
- Restore can materialize directly from a manifest without replaying revision chains.

Service:
- `backend/app/services/published_app_revision_store.py`
- `backend/app/services/published_app_revision_build_dispatch.py`

Build behavior (current):
- Preview-build-created draft revisions are stored already built (`build_status=succeeded`) with source and dist both taken from the same preview snapshot.
- Manual draft version creation is removed.
- Publish no longer waits on a separate app-builder revision build job; it reuses the current preview build snapshot.

## Publish Pipeline
Publish is immediate from the currently visible preview build.

Flow:
1. `POST /admin/apps/{app_id}/versions/{version_id}/publish` resolves the current successful preview build being served in the builder preview.
2. If that preview build was already materialized into a revision, publish reuses it.
3. Otherwise publish materializes a revision directly from the preview build snapshot source/dist pair.
4. Publish pointer updates immediately to that revision and the publish job completes synchronously.

Important current-build rule:
- Publish uses the currently served successful preview snapshot (`current.json` semantics), not the latest attempted rebuild status. If a newer rebuild fails, the visible older snapshot remains publishable.

Key endpoints:
- `POST /admin/apps/{app_id}/versions/{version_id}/publish`
- `GET /admin/apps/{app_id}/publish/jobs/{job_id}`
- `GET /admin/apps/{app_id}/versions/{version_id}/preview-runtime`

Worker/runtime plumbing:
- Celery app/tasks remain available as fallback under `backend/app/workers/`.
- Sandbox publish runner service (in-process async dispatch) is implemented in:
  - `backend/app/services/published_app_publish_runtime.py`
- Publish build-wait + pointer-update worker task:
  - `backend/app/workers/tasks.py` (`publish_version_pointer_after_build_task`)

Publish job observability (current additions):
- Polling response includes optional `stage` (for example `snapshot`, `install`, `build`, `upload`, `finalize`).
- Publish jobs record `last_heartbeat_at` for long-running sandbox publishes.
- Sandbox publish diagnostics may include payload-sync skip metadata indicating live-preview snapshot source-of-truth semantics.

Current publish invariant:
- Publish source of truth is exactly the preview build currently visible to the user, not the latest mutable workspace state.

## Public Runtime Delivery
Published runtime is static bundle delivery with a host-gated runtime/auth shell and a canonical runtime bootstrap contract.

Current published runtime entry/auth model (latest hard-cut):
- Same-URL host-gated runtime is handled by backend host-aware middleware/router for `*.{APPS_BASE_DOMAIN}`.
- Auth-enabled published apps render a centralized backend auth shell at the app URL (no iframe, no frontend `/published/{slug}` auth pages).
- Published app auth now uses an HttpOnly per-app cookie session (`published_app_session`) as the runtime source of truth.
- Published runtime chat uses same-host internal endpoints under `/_talmudpedia/*` and cookie auth (no published-mode localStorage bearer token requirement).

Public endpoints (current):
- Host runtime/auth on app domain (`https://{slug}.{APPS_BASE_DOMAIN}`):
  - same-URL document/asset delivery via host-aware middleware/router
  - `/_talmudpedia/auth/*`
  - `/_talmudpedia/chat/stream`
  - `/_talmudpedia/runtime/bootstrap`
- Preview/runtime APIs (builder preview path mode retained):
  - `GET /public/apps/preview/revisions/{revision_id}/runtime`
  - `GET /public/apps/preview/revisions/{revision_id}/runtime/bootstrap`
  - `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`

Runtime delivery behavior:
- HTML runtime responses inject `window.__APP_RUNTIME_CONTEXT` using the same bootstrap payload schema as `/runtime/bootstrap`.
- Published public runtime endpoints now enforce per-app CORS allowlist (`allowed_origins`, plus published URL).
- Host-gated published runtime HTML (same app host path) injects runtime bootstrap pointing chat stream to `/_talmudpedia/chat/stream`.
- Preview runtime/bootstrap/assets return tokenless URLs and no longer support query-token auth.
- Preview auth is bearer/cookie only, and preview runtime responses set preview cookie from the authenticated principal token for tokenless browser navigation.

Removed path behavior:
- Published runtime/auth/chat path endpoints under `/public/apps/{slug}/*` return `410 PUBLISHED_RUNTIME_PATH_MODE_REMOVED`.
- `GET /public/apps/{slug}/ui` returns `410 UI_SOURCE_MODE_REMOVED`.

## Builder Dependency and Project Validation
Builder validation enforces project/import safety requirements for Vite projects.

Validation service:
- `backend/app/services/apps_builder_dependency_policy.py`

Current policy highlights:
- Valid Vite project shape expected (`package.json`, `index.html`, `src/**`, etc.).
- Security import checks still apply (e.g., block URL imports, block absolute FS imports).
- Package import declarations are not curated by allowlist in current policy.

## End-to-End User Flow (Today)
### Create App
- User selects template (including `fresh-start`).
- Draft revision is created from template files + canonical `.opencode` bootstrap overlay.
- Builder opens with draft preview session.

### Edit in Builder
- File edits sync into active draft sandbox session.
- Preview updates via live dev server behavior.

### Ask Coding-Agent
- Run created with selected/default model and context.
- Agent executes in shared stage workspace for the app+user scope.
- Tool/assistant events stream to chat panel.
- Batch finalizer promotes to live only when active run count reaches zero and at least one completed run exists in the batch.
- Only latest completed run in that finalized batch receives `result_revision_id`/`checkpoint_revision_id`; non-owner completed runs remain null for those fields.

### Publish
- Async publish job performs deterministic build and artifact upload.
- In sandbox publish mode, click-time publish uses the current live preview sandbox snapshot (WYSIWYG) and does not require frontend local draft revision state to be perfectly in sync with the latest backend draft revision ID.
- Frontend may still send publish payload `files`/`entry_file`, but backend sandbox publish ignores file payloads and publishes the current live snapshot.
- App published pointer moves when job succeeds.

### Open Runtime
- Published runtime resolves through runtime descriptor/static artifact URL.
- On the published app host itself, backend now serves either the centralized auth shell or the published runtime HTML at the same URL based on cookie auth state.

### Version Preview Readiness
- Version preview runtime endpoint now fails fast when selected revision dist artifacts are unavailable:
  - `GET /admin/apps/{app_id}/versions/{version_id}/preview-runtime`
  - returns `409 VERSION_BUILD_NOT_READY` with `build_status` and `build_error`
- This replaces delayed asset-path failures and allows frontend to display non-fatal “build not ready” status.

## Operational and Testing Notes
Relevant active test areas:
- Backend:
  - `backend/tests/published_apps/`
  - `backend/tests/coding_agent_api/`
  - `backend/tests/opencode_server_client/`
  - `backend/tests/sandbox_controller/`
- Frontend:
  - `frontend-reshet/src/__tests__/published_apps/`

Notable recent coverage themes:
- run lifecycle and terminal handling,
- cancellation behavior,
- template and draft-dev flows,
- streaming behavior and chat queueing,
- shared-stage sandbox semantics and idle-batch promotion behavior,
- chat-history tool-event persistence/restore on reload.

## Data Model and Contracts (Current)
### Draft-Dev Session Contract
`DraftDevSessionResponse` now exposes count-based activity:
- `has_active_coding_runs: bool` (required)
- `active_coding_run_count: int` (required)

Removed from contract:
- `active_coding_run_id`
- `active_coding_run_status`

### Agent Run Batch-Finalization Fields
`agent_runs` includes:
- `has_workspace_writes BOOLEAN NOT NULL DEFAULT FALSE`
- `batch_finalized_at TIMESTAMPTZ NULL`
- `batch_owner BOOLEAN NOT NULL DEFAULT FALSE`

### Internal Stage Runtime API Hard Cut
`published_app_draft_dev_runtime_client` and dev shim now use scope-based stage methods:
- `prepare_stage_workspace(reset: bool)`
- `snapshot_workspace(stage)` (no run id)
- `promote_stage_workspace()` (no run id)

## Current Constraints and Known Tradeoffs
- Draft and publish paths intentionally optimize for different goals:
  - draft for responsiveness,
  - publish for deterministic output.
- Some infra hardening items (full worker isolation/quotas policy enforcement in production topology) remain deployment/environment dependent.
- `chat-classic` fast-create artifact strategy exists as planning scope; it is not the generalized create path for all templates.

## Document Scope Boundaries
This file is the high-level current-state overview for Apps Builder.
Detailed subtopics remain documented in dedicated docs, especially:
- `backend/documentations/Templates.md`
- `backend/documentations/summary/CustomCodingAgent.md`
- `code_architect/architecture_tree.md`
