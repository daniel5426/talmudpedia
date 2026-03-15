# Apps Builder Current

Last Updated: 2026-03-16

This document is the canonical current-state overview for the Apps Builder system.

## Scope

Apps Builder covers draft editing, preview runtime, coding-agent execution, revision materialization, and publish/runtime delivery for published apps.

## Current Model

- Draft mode uses one shared draft-dev workspace per app with per-user attachment sessions.
- Preview serves the latest successful preview-build snapshot instead of raw live modules.
- Sprite preview builds use polling-based watch detection so out-of-process workspace writes from coding-agent and manual edits reliably trigger rebuilds.
- Coding-agent runs execute against the canonical shared workspace watched by the preview runtime.
- Manual code edits save through the draft-dev workspace, then materialize a new draft revision from the resulting preview build so the builder lands in the same revisioned state as a completed coding-agent edit.
- Published runtime remains static artifact delivery.
- Publish reuses or materializes the currently visible successful preview-build snapshot.
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

## Legacy Detail

The previous detailed overview now lives at `backend/documentations/Plans/AppsBuilder_Current_Implementation_Overview.md` as a legacy pointer.
