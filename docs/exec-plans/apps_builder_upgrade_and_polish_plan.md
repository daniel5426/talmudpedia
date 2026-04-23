Last Updated: 2026-04-23

# Apps Builder Upgrade And Polish Plan

## Scope

Stabilize and speed up the apps builder flow in four areas:

1. New app creation is too slow.
2. Fresh apps incorrectly get a second version before any user edit.
3. Preview shows repeated short "warming/reconnecting" flashes and can interrupt in-progress work.
4. Opening an existing app is still too slow.

## Findings

### 1. New app creation blocks on full bootstrap

The create modal stays open because the frontend waits for `publishedAppsService.create()` to finish before closing and navigating.

Relevant code:
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/admin/apps/page.tsx`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin_routes_apps.py`

The backend create route is synchronous and does all of this before returning:
- create app row
- provision draft workspace
- start preview/runtime services
- wait for watcher-ready build
- materialize the first durable draft revision

The slow path runs through:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_revision_materializer.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_workspace_build_service.py`

Trace evidence from `/tmp/talmudpedia-apps-builder-events.jsonl`:
- `2026-04-22T20:55:14Z` workspace provision requested
- `2026-04-22T20:56:05Z` first durable materialization completed

Observed create time was about 51 seconds end-to-end for a healthy run.

### 2. Fresh apps get `Version 2 • live preview` without user edits

`Version 1` is created intentionally in the create route by materializing the initial workspace with `origin_kind="app_init"`.

Then opening the builder auto-starts the draft-dev session, and heartbeat-side logic may materialize another durable revision with `origin_kind="live_preview"`.

Relevant code:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin_routes_apps.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/workspace/useAppsBuilderSandboxLifecycle.ts`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/workspace/chat/AppsBuilderVersionHistoryPanel.tsx`

This is wrong product behavior and also adds startup work.

### 3. Fingerprint drift is mostly a design bug, not real content drift

The durable build/materialization path computes a canonical backend fingerprint from normalized workspace files plus runtime overlay.

But runtime restore path reuses `live_preview.workspace_fingerprint` from preview metadata instead of recomputing the same canonical fingerprint from restored files.

Relevant code:
- Canonical backend fingerprint path:
  - `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_workspace_build_service.py`
- Drift-prone restore path:
  - `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime.py`

Result:
- one path produces fingerprint A
- another path produces fingerprint B
- startup compares them and may think a new version is needed even when files did not change

### 4. Normal heartbeat is doing too much work

The draft-dev heartbeat is not a cheap keep-alive.

Frontend:
- `DRAFT_DEV_HEARTBEAT_MS = 30_000`
- every heartbeat calls `heartbeatDraftDevSessionQuiet(appId)`
- file: `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/workspace/useAppsBuilderSandboxLifecycle.ts`

Backend heartbeat path:
- refreshes runtime state
- restores or refreshes live workspace snapshot from runtime
- may run `_maybe_materialize_live_workspace(...)`
- file: `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime.py`

Trace evidence shows repeated no-op heartbeats still doing expensive work:
- `2026-04-22T21:52:28Z` heartbeat requested
- `2026-04-22T21:52:36Z` snapshot refreshed from runtime
- `2026-04-22T21:52:41Z` live preview materialization done

This pattern repeats roughly every 30 seconds for the same app even while the preview build remains unchanged.

### 5. Preview flash / micro-reload is caused by reconnect state, not a true app-level navigation bug

The corner "warming/reconnecting" message comes from preview overlay state.

Relevant frontend code:
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/preview/PreviewCanvas.tsx`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/preview/useBuilderPreviewTransport.ts`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/preview/previewLoadingState.ts`

Important behavior:
- `PreviewCanvas` shows a small reconnect overlay whenever transport status becomes `reconnecting`.
- transport becomes `reconnecting` if heartbeat/session state says preview is pending/recovering/syncing, even when an iframe already exists.

So the user-visible flash is consistent with heartbeat-driven transport churn.

Important nuance:
- I did not find evidence that the iframe URL is forced to change on every heartbeat in the healthy path.
- I did find clear evidence that heartbeat repeatedly drives session refresh/materialization work and that the UI exposes this as preview warmup/reconnect state.
- If the underlying app inside the iframe is sensitive to reconnects/HMR resets, that is enough to disrupt in-progress work.

### 6. Opening an existing app is still slow for two reasons

Reason A: initial builder load does more than a simple metadata fetch.

Frontend load path:
- `AppsBuilderWorkspace` waits on both:
  - `getBuilderState(appId)`
  - `getExportOptions(appId)`
- file: `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx`

Reason B: `GET /builder/state` can itself trigger a full runtime heartbeat for an existing serving session.

Relevant backend code:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin_routes_builder.py`

That route currently calls `runtime_service.heartbeat_session(...)` for active sessions before returning builder state.

So "open existing app" can block on:
- builder state fetch
- export options fetch
- heartbeat refresh
- runtime snapshot refresh
- live-preview materialization
- then frontend startup `ensureDraftDevSession(...)` if no reusable session is present

This is why existing-app open is shorter than create, but still too heavy for a simple open.

## Root Causes

1. The create API is synchronous and waits for full preview bootstrap.
2. Heartbeat is overloaded with snapshot refresh and durable-materialization behavior.
3. Durable revision creation is allowed on plain startup/heartbeat.
4. Fingerprint computation is not canonical across all paths.
5. Builder state fetch is not a cheap read; it can perform runtime work.
6. Preview UI currently surfaces transient backend reconnect states directly to the user.

## Upgrade Plan

### Workstream 1: Make heartbeat cheap and side-effect free

Goal:
- heartbeat should only keep the sandbox alive and refresh minimal health metadata

Changes:
- remove durable revision materialization from plain heartbeat path
- stop refreshing full live workspace snapshot on every heartbeat
- only refresh snapshot when explicitly needed:
  - manual save
  - coding run completion
  - restore
  - template reset
  - explicit sync
- keep heartbeat focused on:
  - liveness
  - preview health
  - last activity timestamps

Primary files:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin_routes_builder.py`

### Workstream 2: Stop creating `live_preview` versions on startup

Goal:
- opening the builder should not create a new durable version by itself

Changes:
- in `_maybe_materialize_live_workspace(...)`, if there is no explicit materialization request, do not create a new durable revision
- instead, bind/reuse the current draft revision
- reserve revision creation for explicit save-worthy events

Primary file:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime.py`

### Workstream 3: Unify fingerprint computation

Goal:
- one canonical workspace fingerprint algorithm everywhere

Changes:
- extract or reuse a single backend helper for canonical workspace fingerprinting
- recompute fingerprint from restored files in runtime restore path
- do not trust preview metadata fingerprint as the durable comparison source

Primary files:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_workspace_build_service.py`

### Workstream 4: Decouple create-app UX from full bootstrap

Goal:
- modal closes quickly after app record/workspace is created

Changes:
- split create flow into:
  - fast app creation response
  - async preview bootstrap
- navigate to builder as soon as the app exists
- show builder warmup state there instead of blocking the modal for the whole bootstrap

Primary files:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin_routes_apps.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/admin/apps/page.tsx`

### Workstream 5: Make existing-app open cheap

Goal:
- opening an existing app should feel close to a metadata fetch plus preview attach

Changes:
- keep `GET /builder/state` read-mostly
- remove heartbeat side effects from builder-state fetch
- consider lazy-loading export options after first paint
- keep session ensure/attach off the critical path when a healthy session already exists

Primary files:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin_routes_builder.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx`

### Workstream 6: Smooth preview UX during transient reconnects

Goal:
- no visible preview flash for healthy keep-alive cycles

Changes:
- do not surface reconnect overlay for tiny transient heartbeat states when the existing frame is still usable
- preserve the current iframe unless transport key or normalized preview URL truly changed
- only show blocking warmup UI for real preview loss or explicit restart

Primary files:
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/preview/PreviewCanvas.tsx`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/preview/useBuilderPreviewTransport.ts`
- `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/workspace/useAppsBuilderSandboxLifecycle.ts`

## Recommended Execution Order

1. Remove heartbeat-side materialization and repeated snapshot refresh.
2. Stop startup from creating `live_preview` revisions.
3. Unify fingerprint computation.
4. Make `GET /builder/state` cheap.
5. Move create flow to async bootstrap UX.
6. Polish preview reconnect UI after backend churn is reduced.

## Acceptance Criteria

### Create app

- create modal does not block for tens of seconds
- app opens quickly into builder warmup state
- healthy first open does not create `Version 2`

### Versions

- fresh app has exactly one version until a real save-worthy action happens
- heartbeat/open/reconnect cannot create durable revisions by themselves

### Preview

- healthy steady-state preview does not show periodic reconnect/warmup flashes
- heartbeat does not interrupt in-progress preview flows

### Existing app open

- opening an existing app does not block on heavy heartbeat-side work
- builder state route behaves as a cheap read in the common case

## Notes

- The preview-flash issue and the existing-app-open slowness appear to share the same main root cause: heartbeat currently does expensive state reconciliation on the critical path.
- Fixing heartbeat behavior first should remove a large part of both problems before any frontend polish work.
