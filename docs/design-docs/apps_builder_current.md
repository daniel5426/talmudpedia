# Apps Builder Current

Last Updated: 2026-04-23

This document is the canonical current-state overview for the Apps Builder system.

## Scope

Apps Builder covers draft editing, preview runtime, coding-agent execution, revision materialization, and publish/runtime delivery for published apps.

## Current Model

- Draft mode uses one shared draft-dev workspace per app with per-user attachment sessions.
- The shared live draft-dev workspace is the canonical editable runtime surface; saved revisions are checkpoints, not workspace drivers.
- Preview is a static builder-preview pipeline backed by one persistent Vite/Rollup watch process plus a tiny static file server.
- Fresh app session ensure now returns as soon as the live workspace/session exists and defers first durable `app_init` creation to the first watcher-ready build.
- Sprite preview uses real Vite/Rollup watch mode with persistent graph reuse, not a custom poll-and-fresh-build loop.
- Coding-agent runs execute against the canonical shared workspace watched by the persistent preview build pipeline.
- Live manual code edits are applied incrementally into the shared draft-dev workspace instead of full-workspace resyncs on every debounce.
- Manual code edits save only through `PATCH /builder/draft-dev/session/sync`, and that route now syncs files plus directly materializes the next durable `manual_save` revision from watcher-ready output in the same request.
- Preview always serves the latest successful watcher dist and does not wait for durable revision creation.
- Published runtime remains static artifact delivery.
- Completed write-producing coding-agent turns update the shared live workspace, and coding-run completion is the only automatic post-run trigger that may create the next durable draft revision.
- Coding-agent bootstrap now prefers reusing an existing healthy live workspace/session as-is instead of re-ensuring the workspace against `current_draft_revision_id` on every run.
- Coding-run finalization now uses a row-claimed two-phase flow instead of session-level advisory locks, so duplicate terminal-finalizer entry points can safely converge on one durable revision result.
- Workspace builds are cached per app/workspace fingerprint and reused across retries or repeated version creation for unchanged source state.
- Workspace materialization no longer runs `npm install` or `npm run build`; it snapshots the live workspace, waits for a watcher-ready preview build that matches by fingerprint or current revision token, and promotes that watcher dist into durable bundle storage.
- App creation no longer seeds a provisional queued `Version 1`; the first durable `app_init` revision is created only when the first watcher-ready build exists.
- Draft-dev recovery now prefers the latest persisted live-workspace snapshot for the current revision instead of blindly resyncing from the saved draft revision files.
- Durable dist assets still use the published bundle-storage contract, but local Sprite/dev runtimes now fall back to filesystem-backed bundle storage when the configured local S3 endpoint is unavailable.
- Revision materialization updates draft revision pointers without reattaching the live draft-dev session to the saved revision snapshot.
- Session `revision_id` remains lineage metadata for the live workspace and no longer drives live workspace replacement during coding-run startup.
- The builder preview proxy now serves static preview assets from the promoted current build and exposes `/_talmudpedia/status` directly from backend heartbeat metadata.
- Preview rebuild freshness is driven by watcher status while code-tab freshness remains driven by `live_workspace_snapshot` and `workspace_revision_token`.
- Restore syncs the selected revision back into the live workspace, waits for watcher-ready output, and creates a new durable draft revision with `restored_from_revision_id`.
- Heartbeat is liveness-only and does not refresh snapshots or create revisions.
- Publish only flips `current_published_revision_id` to an already materialized revision inside the request/job-contract response; it does not wait for a build, create a new revision, or dispatch a worker build.
- The previous template catalog was removed, but the repo now includes a new starter pack at `backend/app/templates/published_apps/classic-chat/`.
- Template infrastructure remains active in backend services and app metadata, and the system is moving toward a single canonical starter rather than a broad multi-template catalog.

## Backend Entry Points

- Builder/admin/public routers:
  - `backend/app/api/routers/published_apps_admin.py`
  - `backend/app/api/routers/published_apps_admin_routes_apps.py`
  - `backend/app/api/routers/published_apps_admin_routes_builder.py`
  - `backend/app/api/routers/published_apps_admin_routes_coding_agent_v2.py`
  - `backend/app/api/routers/published_apps_admin_routes_publish.py`
  - `backend/app/api/routers/published_apps_admin_routes_versions.py`
  - `backend/app/api/routers/published_apps_public.py`
- Draft-dev runtime:
  - `backend/app/services/published_app_draft_dev_runtime.py`
  - `backend/app/services/published_app_draft_dev_runtime_client.py`
  - `backend/app/services/published_app_draft_dev_local_runtime.py`
  - `backend/app/services/published_app_workspace_build_service.py`
  - `backend/app/services/published_app_draft_revision_materializer.py`
- Coding-agent runtime:
  - `backend/app/services/published_app_coding_agent_runtime.py`
  - `backend/app/services/published_app_coding_agent_runtime_streaming.py`
  - `backend/app/services/published_app_coding_agent_runtime_sandbox.py`
  - `backend/app/services/published_app_coding_agent_engines/opencode_engine.py`
  - `backend/app/services/opencode_server_client.py`
- Revision/publish/template-related services:
  - `backend/app/services/published_app_revision_store.py`
  - `backend/app/services/published_app_bundle_storage.py`
  - `backend/app/services/published_app_templates.py`

## Frontend Entry Points

- `frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx`
- `frontend-reshet/src/features/apps-builder/workspace/chat/useAppsBuilderChat.ts`
- `frontend-reshet/src/features/apps-builder/workspace/chat/AppsBuilderChatPanel.tsx`
- `frontend-reshet/src/services/published-apps.ts`

## Runtime Behavior Verified In Code

- Draft-dev session APIs are:
  - `GET /admin/apps/{app_id}/builder/draft-dev/session`
  - `POST /admin/apps/{app_id}/builder/draft-dev/session/ensure`
  - `PATCH /admin/apps/{app_id}/builder/draft-dev/session/sync`
  - `POST /admin/apps/{app_id}/builder/draft-dev/session/heartbeat`
  - `DELETE /admin/apps/{app_id}/builder/draft-dev/session`
- Draft preview and version preview now share one canonical preview-auth contract: one `published_app_preview` token shape, one `published_app_preview_token` cookie, and query-once bootstrap through `preview_url`.
- Admin/session responses expose preview auth only through bootstrap-ready `preview_url`; they do not return separate preview-token fields.
- Builder preview keeps a stable iframe/document flow while treating the server-provided preview URL as opaque auth state.
- The builder preview UI now shows a structured warmup/loading state during draft-dev bootstrap instead of a plain unavailable message while no preview URL is attached yet.
- Draft preview session responses now expose `workspace_revision_token` instead of preview-build ids/sequences.
- Draft preview session responses keep `live_preview`, `live_workspace_snapshot`, and `workspace_revision_token` as separate contracts; revision-token changes are no longer preview rebuild triggers.
- Coding-agent APIs live under `/admin/apps/{app_id}/coding-agent/v2/*`.
- The coding-agent chat contract is session-native: builder chat uses `/chat-sessions/*`, one product chat session maps to one OpenCode session, and live updates flow through one session SSE stream.
- The open builder chat session now treats live SSE as the source of truth for in-flight conversation state; history endpoints are used for initial load/reopen and older-history pagination instead of rewriting the visible active timeline after each idle.
- Version preview inspection lives at `GET /admin/apps/{app_id}/versions/{version_id}/preview-runtime`.
- Version publish lives at `POST /admin/apps/{app_id}/versions/{version_id}/publish` and requires existing durable dist.
- Publish job status lives at `GET /admin/apps/{app_id}/publish/jobs/{job_id}`.

## Template Reset State

- Previous published-app template packs were deleted from `backend/app/templates/published_apps/`.
- `published_app_templates.py` remains the template loader/bootstrap integration point.
- A new starter project now exists at `backend/app/templates/published_apps/classic-chat/`, and it now includes a modular chat-first base page aligned to the platform playground interaction model.
- The starter is now normalized into the backend template-pack contract with canonical key `classic-chat`.
- `template_key` is still part of the current app/revision model and related APIs, so the codebase has not yet completed a full hard cut away from template selection semantics.
- `classic-chat` should be treated as the fresh replacement starter, not as a continuation of the deleted catalog.

## Canonical Related Docs

- `docs/product-specs/apps_builder_preview_and_versioning_spec.md`
- `docs/product-specs/published_apps_spec.md`
- `docs/product-specs/runtime_sdk_host_anywhere_spec.md`
- `docs/design-docs/coding_agent_runtime_current.md`
- `docs/design-docs/unified_preview_auth_contract.md`
- `docs/references/classic_chat_template_reference.md`

## Historical Context

- `docs/design-docs/apps_builder_live_workspace_hmr_architecture.md` is retained as a historical note for the retired Vite dev-server/HMR design.

## Runtime Surface Note

- Builder-hosted and published same-origin runtime continues to use the host runtime/auth shell model.
- Host-anywhere published clients now use the separate external runtime surface under `/public/external/apps/{slug}/*`.
- Both surfaces share the same underlying published-app runtime execution core and stream contract.

## Legacy Detail

The previous detailed overview now lives at `backend/documentations/Plans/AppsBuilder_Current_Implementation_Overview.md` as a legacy pointer.
