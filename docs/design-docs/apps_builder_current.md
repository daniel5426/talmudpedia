# Apps Builder Current

Last Updated: 2026-03-16

This document is the canonical current-state overview for the Apps Builder system.

## Scope

Apps Builder covers draft editing, preview runtime, coding-agent execution, revision materialization, and publish/runtime delivery for published apps.

## Current Model

- Draft mode uses one shared draft-dev workspace per app with per-user attachment sessions.
- Preview is a live Vite dev server running directly against the shared draft-dev workspace.
- Sprite preview uses Vite watch polling, not a custom preview-build snapshot watcher.
- Coding-agent runs execute against the canonical shared workspace watched by the Vite preview runtime.
- Live manual code edits are applied incrementally into the shared draft-dev workspace instead of full-workspace resyncs on every debounce.
- Manual code edits save through the draft-dev workspace, then materialize a durable draft revision from a cached workspace-build record keyed by the current workspace fingerprint.
- Published runtime remains static artifact delivery.
- Completed write-producing coding-agent runs materialize a durable draft revision through the same cached workspace-build path.
- Workspace builds are cached per app/workspace fingerprint and reused across retries or repeated version creation for unchanged source state.
- Draft-dev recovery now prefers the latest persisted live-workspace snapshot for the current revision instead of blindly resyncing from the saved draft revision files.
- Durable dist assets still use the published bundle-storage contract, but local Sprite/dev runtimes now fall back to filesystem-backed bundle storage when the configured local S3 endpoint is unavailable.
- Revision materialization updates draft revision pointers without reattaching the live draft-dev session to the saved revision snapshot.
- Publish only flips `current_published_revision_id` to an already materialized revision; it does not build or create a new revision.
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
  - `backend/app/services/published_app_publish_runtime.py`

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
- Draft preview responses carry off-URL auth fields such as `preview_auth_token`.
- Preview/runtime URLs use explicit runtime query context such as `runtime_mode`, `runtime_base_path`, and `runtime_token`.
- The preview iframe is expected to keep a stable URL across routine auth-token refreshes; token rotation should not force full iframe reloads.
- Draft preview session responses now expose `workspace_revision_token` instead of preview-build ids/sequences.
- Coding-agent APIs live under `/admin/apps/{app_id}/coding-agent/v2/*`.
- Version preview inspection lives at `GET /admin/apps/{app_id}/versions/{version_id}/preview-runtime`.
- Publish job status lives at `GET /admin/apps/{app_id}/publish/jobs/{job_id}`.

## Template Reset State

- Previous published-app template packs were deleted from `backend/app/templates/published_apps/`.
- `published_app_templates.py` remains the template loader/bootstrap integration point.
- A new starter project now exists at `backend/app/templates/published_apps/classic-chat/`, and it now includes a modular chat-first base page aligned to the platform playground interaction model.
- The starter is now normalized into the backend template-pack contract with canonical key `classic-chat`.
- `template_key` is still part of the current app/revision model and related APIs, so the codebase has not yet completed a full hard cut away from template selection semantics.
- `classic-chat` should be treated as the fresh replacement starter, not as a continuation of the deleted catalog.

## Canonical Related Docs

- `docs/product-specs/published_apps_spec.md`
- `docs/product-specs/runtime_sdk_host_anywhere_spec.md`
- `docs/design-docs/coding_agent_runtime_current.md`
- `docs/references/classic_chat_template_reference.md`

## Runtime Surface Note

- Builder-hosted and published same-origin runtime continues to use the host runtime/auth shell model.
- Host-anywhere published clients now use the separate external runtime surface under `/public/external/apps/{slug}/*`.
- Both surfaces share the same underlying published-app runtime execution core and stream contract.

## Legacy Detail

The previous detailed overview now lives at `backend/documentations/Plans/AppsBuilder_Current_Implementation_Overview.md` as a legacy pointer.
