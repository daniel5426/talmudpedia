# Apps Builder Current Implementation Overview

Last Updated: 2026-02-23

## Purpose
This document is the current-state overview of the Apps Builder system (not a future implementation plan). It summarizes how the builder works today across backend, frontend, runtime, coding-agent, revision persistence, and publish/runtime delivery.

## Product-Level Model
Apps Builder currently operates in two execution modes:
- Draft mode (builder editing + preview): optimized for speed and iteration.
- Publish mode (immutable runtime artifact): optimized for determinism and stability.

Core implementation choices in current state:
- Draft preview uses a persistent draft-dev sandbox session per app/user.
- Coding-agent runs use the same sandbox as preview, with stage/live isolation inside that sandbox.
- Published runtime is static artifact delivery (`vite_static`) and no longer source-UI compilation.

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
Draft preview uses draft-dev sandbox sessions and no longer uses browser-side compile for app-builder runtime.

Session lifecycle APIs:
- `GET /admin/apps/{app_id}/builder/draft-dev/session`
- `POST /admin/apps/{app_id}/builder/draft-dev/session/ensure`
- `PATCH /admin/apps/{app_id}/builder/draft-dev/session/sync`
- `POST /admin/apps/{app_id}/builder/draft-dev/session/heartbeat`
- `DELETE /admin/apps/{app_id}/builder/draft-dev/session`

Important runtime behavior:
- Persistent dev server in sandbox for fast feedback/HMR during editing.
- Sync path avoids unnecessary rewrites to reduce no-op restarts.
- Builder preview iframe URL stays stable and tokenless across heartbeat/token refresh.
- Draft-dev session response carries off-URL auth fields (`preview_auth_token`, `preview_auth_expires_at`) for iframe auth channel updates.
- Draft-dev preview URLs are decorated only with runtime routing query params so template runtime clients can resolve chat base path in preview:
  - `runtime_mode=builder-preview`
  - `runtime_base_path={resolved_runtime_api_base}/public/apps/preview/revisions/{revision_id}`
- Builder sends preview auth to iframe runtime via `window.postMessage` (`talmudpedia.preview-auth.v1`), and runtime SDK uses bearer auth headers for preview chat stream calls.

## Coding-Agent Runtime (Current)
### Single-Sandbox, Stage/Live Model
Coding-agent execution is now single-sandbox with internal stage/live workspaces:
- Live workspace: preview app root used by Vite.
- Stage workspace: `.talmudpedia/stage/<run_id>/workspace` inside same sandbox.

Run flow:
1. Create run (`POST /coding-agent/runs`) and resolve active preview sandbox session.
2. Prepare stage workspace from live snapshot.
3. Start OpenCode against stage workspace path.
4. Stream run events to frontend (assistant/tool/terminal events).
5. On successful write run, promote stage -> live.
6. Persist revision/checkpoint as needed.

### Locking and Idempotency
- Draft-dev session tracks active run lock metadata.
- Builder writes can be blocked while run is active (`CODING_AGENT_RUN_ACTIVE`).
- Run create accepts `client_message_id` for idempotent submission.

### Chat/History
- Chat sessions and chat messages are persisted server-side.
- Frontend can resume chat sessions and reuse `chat_session_id` across runs.

## OpenCode Integration
OpenCode is the default engine path in current state.

Current integration model:
- No OpenCode MCP contract registration path.
- Project-local custom tool bootstrap (`.opencode/*`) is seeded per run if needed.
- `read_agent_context` is the consolidated custom tool for selected-agent context reads.
- Run startup fails closed when required bootstrap/context seeding fails.

Recent stability hardening reflected in code/docs:
- Improved terminal event handling to reduce hanging runs.
- Stream handling tuned for incremental assistant deltas.
- Cancel path supports sandbox-routed cancellation and run finalization semantics.

## Revision Persistence Model
Current revision persistence uses snapshot-manifest + content-addressed blob storage.

Core behavior:
- Manifest maps `path -> blob_hash`.
- Blobs are stored under revision-blob prefix in object storage.
- Restore can materialize directly from a manifest without replaying revision chains.

Service:
- `backend/app/services/published_app_revision_store.py`

## Publish Pipeline
Publish is asynchronous and deterministic.

Flow:
1. Optional autosave payload accepted at publish request.
2. Publish job created/enqueued.
3. Clean build runs for publish target revision.
4. Dist artifacts uploaded to immutable storage prefix.
5. Publish pointer/url updates only on successful completion.

Key endpoints:
- `POST /admin/apps/{app_id}/publish`
- `GET /admin/apps/{app_id}/publish/jobs/{job_id}`

Worker/runtime plumbing:
- Celery app and tasks are under `backend/app/workers/`.

## Public Runtime Delivery
Published runtime is static-only delivery with runtime descriptor APIs and a canonical runtime bootstrap contract.

Public endpoints:
- `GET /public/apps/{slug}/runtime`
- `GET /public/apps/{slug}/runtime/bootstrap`
- `GET /public/apps/preview/revisions/{revision_id}/runtime`
- `GET /public/apps/preview/revisions/{revision_id}/runtime/bootstrap`
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`
- `POST /public/apps/{slug}/auth/exchange` (external OIDC JWT -> platform session token)

Runtime delivery behavior:
- HTML runtime responses inject `window.__APP_RUNTIME_CONTEXT` using the same bootstrap payload schema as `/runtime/bootstrap`.
- Published public runtime endpoints now enforce per-app CORS allowlist (`allowed_origins`, plus published URL).
- Preview runtime/bootstrap/assets return tokenless URLs and no longer support query-token auth.
- Preview auth is bearer/cookie only, and preview runtime responses set preview cookie from the authenticated principal token for tokenless browser navigation.

Removed path behavior:
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
- Agent executes in stage workspace.
- Tool/assistant events stream to chat panel.
- On success with edits, stage promotes to live and revision/checkpoint can be recorded.

### Publish
- Async publish job performs deterministic build and artifact upload.
- App published pointer moves when job succeeds.

### Open Runtime
- Published runtime resolves through runtime descriptor/static artifact URL.

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
- stage/live sandbox semantics.

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
