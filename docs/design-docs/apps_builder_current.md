# Apps Builder Current

Last Updated: 2026-03-15

This document is the canonical current-state overview for the Apps Builder system.

## Scope

Apps Builder covers draft editing, preview runtime, coding-agent execution, revision materialization, and publish/runtime delivery for published apps.

## Current Model

- Draft mode uses one shared draft-dev workspace per app with per-user attachment sessions.
- Preview serves the latest successful preview-build snapshot instead of raw live modules.
- Coding-agent runs execute against the canonical shared workspace watched by the preview runtime.
- Published runtime remains static artifact delivery.
- Publish reuses or materializes the currently visible successful preview-build snapshot.
- The repo is currently between template generations: `backend/app/templates/published_apps/` is intentionally empty after the previous app template packs were removed.
- Template infrastructure still exists in backend services and app metadata, but there is no active checked-in published-app template catalog right now.

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
- `published_app_templates.py` remains the template loader/bootstrap integration point, but the checked-in catalog has been reset to empty.
- `template_key` is still part of the current app/revision model and related APIs, so the codebase has not yet completed a full hard cut away from template selection semantics.
- The next template should be treated as a fresh replacement, not an incremental continuation of the deleted catalog.

## Canonical Related Docs

- `docs/product-specs/published_apps_spec.md`
- `docs/product-specs/runtime_sdk_host_anywhere_spec.md`
- `docs/design-docs/coding_agent_runtime_current.md`

## Legacy Detail

The previous detailed overview now lives at `backend/documentations/Plans/AppsBuilder_Current_Implementation_Overview.md` as a legacy pointer.
