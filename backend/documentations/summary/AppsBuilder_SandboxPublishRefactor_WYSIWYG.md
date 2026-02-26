# Apps Builder Sandbox Publish Refactor (WYSIWYG)

Last Updated: 2026-02-26

## Summary
Implemented a feature-flagged sandbox publish path (`APPS_PUBLISH_USE_SANDBOX_BUILD=1`) that publishes from the current draft-dev live preview workspace instead of the Celery worker draft-revision build path.

## What Changed
- Added in-process sandbox publish runner: `backend/app/services/published_app_publish_runtime.py`
- Added publish job `stage` + `last_heartbeat_at` fields (model + Alembic migration)
- `POST /admin/apps/{app_id}/publish` now:
  - uses live preview source semantics only when sandbox publish flag is enabled
  - requires active draft-dev session in sandbox mode
  - rejects concurrent publishes per app in sandbox mode
  - still supports legacy Celery publish behavior when sandbox flag is disabled
- Draft-dev sandbox controller/runtime/client gained:
  - publish workspace snapshot prep (`/publish/prepare`)
  - scoped workspace sync (`/workspace/sync`)
  - scoped command cwd (`workspace_path`)
  - workspace archive export (`/workspace/archive`)
- Draft-dev session stop is blocked while a publish job is active
- Draft-dev idle expiry skips sessions with active publish jobs

## Publish Semantics (Sandbox Mode)
- Source of truth: live preview workspace
- Publish input: frozen copy of live preview at publish click
- Build runs in isolated publish workspace: `.talmudpedia/publish/current/workspace`
- Backend creates a draft checkpoint revision from the frozen snapshot before finalize

## Compatibility / Rollout
- Celery publish path remains intact as fallback when `APPS_PUBLISH_USE_SANDBOX_BUILD` is disabled.
- Existing publish polling contract remains (`queued|running|succeeded|failed`) with optional `stage` added.

## Tests Added/Updated
- Added route guard tests under `backend/tests/apps_publish_sandbox/`
- Updated sandbox controller shim tests for new endpoints and `workspace_path` command execution
