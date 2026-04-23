Last Updated: 2026-04-23

# Apps Builder Preview And Versioning Spec

This document is the canonical product/runtime spec for Apps Builder preview, manual save, and draft version creation.

## Core Contract

- Preview and durable versioning are separate paths.
- Preview always serves the latest successful watcher dist.
- Durable draft versions are created only by explicit triggers.
- Durable dist artifacts always come from the watcher-backed build pipeline.
- Builder open, startup, heartbeat, and preview polling must not create draft versions.

## Preview Path

- The shared live workspace is the editable source of truth during draft editing.
- The live preview watcher observes that workspace and produces the latest successful dist.
- Builder preview always uses the latest successful watcher dist.
- Preview refresh does not wait for durable revision creation.
- Preview status and builder-state reads are metadata reads in the normal path; they must not perform implicit versioning work.

## Durable Version Path

Durable draft revisions may be created only by these triggers:

- `app_init`
- `manual_save`
- `coding_run`
- `restore`
- `template_reset`

Durable draft revisions may not be created by:

- builder open
- startup ensure
- heartbeat
- preview polling
- passive session recovery
- watcher rebuild by itself

## App Creation

- `POST /admin/apps` creates the app row and starter workspace metadata only.
- No fake queued `Version 1` is created during app creation.
- The first real `Version 1 • app_init` is created only after the first watcher-ready build exists.
- Fresh app session ensure returns as soon as the live workspace/session exists; it must not block on first durable version creation.

## Manual Save

- Manual save syncs the editor files into the shared live workspace.
- Manual save then directly calls the watcher-backed draft materializer with `origin_kind="manual_save"`.
- Manual save returns only after the durable revision has been created or reused.
- Manual save must not queue deferred materialization metadata for later heartbeat consumption.

## Coding Run

- Coding runs update the shared live workspace while preview keeps following watcher output.
- On coding-run completion, finalization snapshots the final workspace state and decides whether a durable revision is needed.
- A coding run creates at most one durable revision for the final run state.

## Heartbeat

- Heartbeat is liveness-only.
- Heartbeat may extend expiry, ping sandbox health, and refresh lightweight preview metadata.
- Heartbeat must not refresh live workspace snapshots.
- Heartbeat must not create, reuse, or rebind durable revisions.

## Builder State Read Path

- `GET /admin/apps/{app_id}/builder/state` is read-only in the common case.
- It returns stored app state, stored draft-dev session state, and stored preview metadata.
- It must not heartbeat the runtime or create versions during read.

## Source Of Truth Summary

- Live editable state: shared live workspace.
- Live preview output: latest successful watcher dist.
- Durable saved history: materialized draft revisions backed by watcher-ready builds.

## Canonical References

- `backend/app/api/routers/published_apps_admin_routes_apps.py`
- `backend/app/api/routers/published_apps_admin_routes_builder.py`
- `backend/app/api/routers/published_apps_admin_routes_versions.py`
- `backend/app/api/routers/published_apps_builder_preview_proxy.py`
- `backend/app/services/published_app_draft_dev_runtime.py`
- `backend/app/services/published_app_draft_revision_materializer.py`
- `backend/app/services/published_app_workspace_build_service.py`
- `frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx`
- `frontend-reshet/src/features/apps-builder/workspace/useAppsBuilderSandboxLifecycle.ts`
