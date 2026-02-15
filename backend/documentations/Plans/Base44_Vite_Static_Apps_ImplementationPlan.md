# Base44-Style Option A Implementation Plan (Vite Static Apps + Shared Backend)

Last Updated: 2026-02-15

## Summary
Move Apps Builder to a dual-mode architecture:
- Draft Dev Mode: persistent per-user+app Vite dev sandbox with HMR for instant preview.
- Publish Build Mode: async full clean worker build (`npm install` + `npm run build`) on publish, then upload immutable artifacts for runtime serving.

## Contradiction Resolution (2026-02-14)
This plan previously stated that publish promotes existing draft artifacts without rebuilding. That is now superseded.
- Draft mode is non-deterministic and optimized for speed (sandbox dev server, incremental sync, no dist upload, no per-keystroke revisions).
- Publish mode is deterministic and always runs a full clean build in an async publish job before switching `current_published_revision_id`.

## Implementation Status Snapshot (as of 2026-02-14)
Implemented:
- Filesystem-backed template packs under `backend/app/templates/published_apps/` with manifest loading and Vite `base: "./"` validation.
- Revision build lifecycle schema/model fields (`build_status`, `build_seq`, `build_error`, timing fields, `dist_storage_prefix`, `dist_manifest`, `template_runtime`) with Alembic migration.
- Curated dependency policy module and admin validator integration (Vite root file policy + pinned package validation).
- Admin build status/retry endpoints:
  - `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
  - `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`
- Public runtime descriptor + preview descriptor + preview asset proxy endpoints:
  - `GET /public/apps/{slug}/runtime`
  - `GET /public/apps/preview/revisions/{revision_id}/runtime`
  - `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`
- Preview runtime URL now resolves to entry HTML (`.../assets/index.html`) and derives path from request context (no hardcoded `/api/py` prefix).
- Preview iframe auth bridge implemented: runtime appends one-time `preview_token` query, asset route mints HttpOnly cookie, subsequent chunk/css requests authenticate via cookie.
- Async publish job schema and worker flow (`published_app_publish_jobs`) with full-build execution path.
- Queue wiring for `apps_build` and real `build_published_app_revision_task` execution flow (`npm ci`, `npm run build`, `dist` manifest, object upload).
- Frontend service contracts for draft-dev session + publish job endpoints.
- Builder preview switched from in-browser compile/build polling to draft-dev session lifecycle (`ensure/sync/heartbeat`) in apps builder workspace.
- Draft-dev stability hardening:
  - local runtime sync now writes files only when content changes (prevents unnecessary Vite restarts from no-op syncs).
  - runtime service now auto-recovers by re-starting session when sync reports a stale/non-running sandbox.
  - workspace sync fingerprint excludes revision ID and avoids redundant post-save sync churn.
  - "Open App" in builder now opens published runtime only for published apps; otherwise it ensures draft-dev and opens preview instead.
- Published runtime page is static-only and redirect-only (`/public/apps/{slug}/runtime` -> `published_url`).
- Publish now enqueues async full-build jobs and no longer gates on draft `build_status`.
- Public source UI endpoints are hard-removed and return `410 UI_SOURCE_MODE_REMOVED`.

Partially implemented:
- Worker hard-isolation controls (container hardening, resource quotas, restricted egress policy) and dedicated Node worker image rollout.
- Build queue locking strategy (`apps_build:{app_id}` single-flight lock) is not implemented yet.

Pending:
- Migration/backfill script for existing revisions and big-bang cutover execution.
- Fast-create prebuilt artifact path for initial app creation (chat-classic pilot) is not implemented yet.

Locked choices:
- Build engine: Celery queue + dedicated Node build worker image.
- Asset storage/serving: object storage + CDN.
- Dependency policy: curated semi-open package set.
- Build trigger: Draft mode uses persistent sandbox dev sessions; Publish mode always rebuilds from latest saved snapshot.
- Draft access: backend proxy with preview token.
- Rollout: big-bang switch.
- Published URL shape: CDN path per revision.
- API origin: same-origin gateway (`/api/py` proxied on app domain).
- Template source: filesystem template packs.
- Artifact identity: immutable outputs are produced during publish jobs and attached to published revisions.
- Vite asset base: relative paths (`base: "./"`) so nested CDN/proxy paths resolve chunks correctly.
- Build queue semantics: one active build per app; stale worker completions ignored via monotonic `build_seq`.

## Current-State Grounding (from repo)
- Builder policy now enforces Vite project + curated dependency rules in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin.py`.
- Builder preview now uses draft-dev sandbox session lifecycle in `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx`.
- Published runtime page now uses static-only redirect behavior in `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/published/[appSlug]/page.tsx`.
- Public runtime API now includes runtime descriptor and preview asset proxy endpoints in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_public.py`.
- Celery + Redis already exist in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/workers/celery_app.py` and `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/workers/tasks.py`.

## Architecture Changes

## 1) Template System: filesystem Vite template packs
Status: Implemented.
- Replace string-built template code in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_templates.py` with filesystem-backed packs.
- Add template pack root: `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/templates/published_apps/`.
- Add one folder per template key (`chat-classic`, `chat-editorial`, `chat-neon`, `chat-soft`, `chat-grid`), each containing a full Vite SPA project baseline.
- Add template manifest per pack (`template.manifest.json`) with metadata (`key`, `name`, `description`, `thumbnail`, `tags`, `entry_file`).
- Keep existing 5 keys unchanged for API compatibility.
- Keep shared backend runtime SDK in each template project as source code inside pack.
- Require template `vite.config.ts` to set `base: "./"`; reject templates/config patches that set absolute base paths.

## 2) Revision model upgrade for static bundle lifecycle
Status: Implemented (except deprecated column removal follow-up).
- Add Alembic migration extending `published_app_revisions` in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/db/postgres/models/published_apps.py`.
- Add columns:
- `build_status` (`queued|running|succeeded|failed`, default `queued`)
- `build_seq` (integer, default `0`; incremented every enqueue)
- `build_error` (nullable text)
- `build_started_at` (nullable timestamp)
- `build_finished_at` (nullable timestamp)
- `dist_storage_prefix` (nullable string)
- `dist_manifest` (nullable JSONB; includes entry HTML + asset list + hashes)
- `template_runtime` (string, default `vite_static`)
- Keep existing `files` and `entry_file` as source-of-truth project files.
- Keep `compiled_bundle` as deprecated/unused field for migration compatibility, then remove in follow-up migration.

## 3) Curated semi-open dependency policy
Status: Implemented.
- Add policy module `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/apps_builder_dependency_policy.py`.
- Add curated allowlist catalog (package -> pinned allowed versions).
- Validation rules:
- `package.json` required in project root.
- Bare imports must be declared in `dependencies`/`devDependencies`.
- Declared packages must exist in curated catalog.
- Declared versions must match allowed pinned versions.
- URL imports and absolute filesystem imports remain forbidden.
- Local/relative imports allowed per Vite resolution.
- Allow root files needed for Vite (`index.html`, `package.json`, `vite.config.ts`, `tsconfig*.json`, `postcss.config.*`, `tailwind.config.*`, `src/**`, `public/**`).

## 4) Build pipeline (Celery + Node image)
Status: Partially implemented.
- Add new Celery task in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/workers/tasks.py`:
- `build_published_app_revision_task(revision_id, tenant_id, app_id, slug, build_kind)`
- Task flow:
- Load revision files from DB.
- Validate project + dependency policy.
- Materialize project to temp dir.
- Run `npm ci` (with cached npm directory) + `npm run build`.
- Enforce per-job isolation/hard limits: dedicated temp dir, no host mounts, bounded CPU/memory, timeout, and restricted outbound network policy.
- Read `dist/`, produce normalized `dist_manifest`.
- Upload `dist/` to object storage under deterministic prefix:
- `apps/{tenant_id}/{app_id}/revisions/{revision_id}/dist/...`
- Before final write, verify task `build_seq` still matches revision row `build_seq`; otherwise mark task result stale and discard.
- Update revision build columns to `succeeded`/`failed` only when sequence matches.
- Add build queue routing in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/workers/celery_app.py`:
- queue `apps_build`.
- Use a per-app lock (`apps_build:{app_id}`) so only one build runs per app at a time; newest queued sequence is authoritative.
- Add worker runtime image (new Dockerfile) with Python + Node LTS + npm for Celery worker pods/containers.
Current gap:
- Worker runtime image + isolation controls (resource/egress/container hardening) are not completed yet.

## 5) Object storage + CDN integration
Status: Partially implemented.
- Add storage service `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_bundle_storage.py` (S3-compatible via boto3).
- Add config envs:
- `APPS_BUNDLE_BUCKET`
- `APPS_BUNDLE_REGION`
- `APPS_BUNDLE_ENDPOINT`
- `APPS_BUNDLE_ACCESS_KEY`
- `APPS_BUNDLE_SECRET_KEY`
- `APPS_CDN_BASE_URL`
- `APPS_CDN_PUBLIC_PREFIX` (default `/apps`)
- Published URL contract:
- `published_url = {APPS_CDN_BASE_URL}{APPS_CDN_PUBLIC_PREFIX}/{slug}/{published_revision_id}/`
- Publish flow:
- create async publish job from latest draft snapshot (auto-save payload optional)
- run clean worker build (`npm install` + `npm run build`)
- upload `dist/` to published revision prefix (`.../revisions/{published_revision_id}/dist/...`)
- persist `dist_storage_prefix` + `dist_manifest`, then atomically switch published revision pointer and `published_url`
- if full build/upload fails, publish job moves to `failed` and app remains on previous published revision.
Current gap:
- Full CDN published URL contract is not final yet (`_build_published_url` still drives runtime URL in current admin router).

## 6) Admin API contract updates
Status: Implemented.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin.py`:
- Update builder revision create/reset flows to:
- create revision with `build_status=queued`
- increment `build_seq`
- do not enqueue heavy draft build task
- return revision including build fields.
- Add build status endpoint:
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
- Add retry endpoint:
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`
- Update publish endpoint behavior:
- `POST /admin/apps/{app_id}/publish` returns `publish_job` immediately.
- Optional autosave payload (`base_revision_id`, `files`, `entry_file`) is persisted before enqueue.
- Publish jobs are tracked via `GET /admin/apps/{app_id}/publish/jobs/{job_id}`.
- Publish no longer gates on draft revision `build_status`; determinism is enforced by full publish build.
- Remove React-only import allowlist enforcement in project validator.
- Replace with Vite project + dependency policy validation.
## 7) Public runtime API contract updates
Status: Implemented.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_public.py`:
- Add runtime descriptor endpoint:
- `GET /public/apps/{slug}/runtime`
- Response fields:
- `app_id`, `slug`, `revision_id`, `runtime_mode: "vite_static"`, `published_url`, `asset_base_url`, `api_base_path: "/api/py"`.
- Keep `/public/apps/{slug}/config` for auth/status metadata.
- `/public/apps/{slug}/ui` is removed and returns `410 UI_SOURCE_MODE_REMOVED` in all modes.
- Add draft preview asset proxy endpoint:
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`
- Requires preview token principal validation, then streams object storage asset.
- Add preview runtime descriptor endpoint:
- `GET /public/apps/preview/revisions/{revision_id}/runtime`
- Returns `preview_url` pointing to proxy entry HTML (`index.html` or manifest `entry_html`) and `asset_base_url` for asset root.
- Preview auth sources supported for draft assets:
- `Authorization: Bearer <preview_token>`
- `preview_token` query parameter (used by iframe bootstrap)
- HttpOnly cookie `published_app_preview_token` (set on first asset response)

## 8) Frontend changes
Status: Partially implemented.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/published-apps.ts`:
- extend builder state with `draft_dev`.
- add draft-dev session and publish-job endpoint contracts.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/preview/PreviewCanvas.tsx`:
- remove `compileReactArtifactProject` path for app-builder preview.
- iframe points directly to sandbox `draft_dev.preview_url`.
- show dev-session statuses: `starting/running/stopped/expired/error`.
- remove draft build-status polling from preview flow.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/published-runtime.ts`:
- add `getRuntime()` endpoint.
- remove reliance on UI source files for public runtime.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/published/[appSlug]/page.tsx`:
- big-bang: replace client compile path with redirect flow:
- fetch config/runtime
- if published + runtime available -> `window.location.replace(published_url)`
Current gap:
- Dedicated static app auth UX migration on runtime host is still pending.

## 9) Migration plan (big-bang)
Status: Pending.
- Add migration script/service:
- For all existing `published_app_revisions`:
- inject required Vite root files if missing.
- preserve existing `src/**` and `public/**`.
- ensure valid `package.json` with curated dependencies.
- ensure `package-lock.json` exists and matches curated dependency pins (generate lockfile during migration when missing).
- mark revisions `build_status=queued`.
- increment `build_seq` before enqueue.
- enqueue builds for all current published revisions first, then draft revisions.
- Cutover rule:
- Switch runtime to static only after all currently published revisions succeed.
- If any published revision fails build:
- set app status `paused` with actionable build error; do not silently serve broken runtime.
- Rollback switch:
- No source-UI rollback path; static runtime is canonical.

## 10) Fast-create plan for prebuilt artifacts (`chat-classic` pilot)
Status: Planned (targeted next).

Goal:
- Remove worker build latency from initial create for `chat-classic` by reusing CI-built immutable artifacts.

Scope:
- In scope now: `chat-classic` only.
- Out of scope now: `chat-grid`, `chat-editorial`, `chat-neon`, `chat-soft`.

### A) CI prebuild + immutable artifact publication
- Add CI job to build only `backend/app/templates/published_apps/chat-classic` and publish `dist/` once per template hash.
- Compute canonical template hash from the same normalized file set used by loader/build seeding (`build_template_files("chat-classic")`), serialized with sorted keys.
- Publish under immutable prefix:
- `apps/templates/chat-classic/{template_hash}/dist/...`
- Persist build metadata object:
- `apps/templates/chat-classic/{template_hash}/artifact.json`
- Include at minimum:
- `template_key`, `template_hash`, `dist_manifest`, `created_at`, `build_tool_versions`.

### B) App creation fast path (no worker build)
- Change create flow in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin.py`:
- `POST /admin/apps` for `template_key=chat-classic` first resolves latest published template artifact metadata.
- Create draft revision with:
- `build_status=succeeded`
- `build_seq=1`
- `dist_manifest` from artifact metadata
- `dist_storage_prefix` set after copy
- Copy artifact into per-revision prefix using storage copy:
- source: `apps/templates/chat-classic/{template_hash}/dist`
- destination: `apps/{tenant_id}/{app_id}/revisions/{revision_id}/dist`
- Keep `files` snapshot seeded from template source (for future edits), but skip enqueueing `build_published_app_revision_task`.
- Fallback behavior:
- If artifact metadata is missing/corrupt or copy fails, fallback to current worker build path and emit structured fallback reason in logs/metrics.

### C) Runtime config injection (avoid template rebuild per app metadata)
- Add runtime config payload endpoint for published runtime:
- `GET /public/apps/{slug}/runtime-config`
- Add preview variant for draft runtime:
- `GET /public/apps/preview/revisions/{revision_id}/runtime-config`
- `chat-classic` runtime bootstrap should fetch this payload at startup and derive per-app values from it (for example: app slug, runtime mode, API base path, auth settings, display name).
- Keep immutable assets tenant-agnostic; move app-specific values out of compiled JS/HTML.

### D) Keep worker builds for user code edits only
- Initial create (`POST /admin/apps`) for `chat-classic`: no worker build.
- Keep draft-dev sync on builder mutations (`POST /admin/apps/{app_id}/builder/revisions`) for preview speed.
- Keep clean worker builds only in publish jobs (`POST /admin/apps/{app_id}/publish`).
- Optional optimization after pilot:
- if a new revision hash matches the base/template artifact hash, copy artifacts and mark succeeded without worker build.

### E) Data/API additions
- Add internal template artifact resolver service (new module under `backend/app/services/`) that maps `(template_key, template_hash)` to artifact metadata/prefix.
- Add build status diagnostics fields/messages to indicate fast-path vs worker-path provenance.
- No breaking public API contract changes required for this pilot; runtime-config endpoints are additive.

### F) Acceptance criteria for pilot
- Creating a `chat-classic` app returns a draft revision already in `build_status=succeeded`.
- No `apps_build` Celery task is enqueued during initial create for `chat-classic`.
- Builder preview URL is available immediately after create (no build poll wait).
- Publish still runs a full clean async build before serving updated immutable artifacts.
- If fast path cannot run, fallback path still preserves current correctness.

### G) Rollout plan
- Phase 1: shadow mode in CI (publish artifact metadata + dist, no runtime usage).
- Phase 2: enable fast-create for internal tenants only via env flag.
- Phase 3: enable for all `chat-classic` creates once fallback/error rate and latency are acceptable.
- Phase 4: decide expansion template-by-template (`chat-grid`, `chat-editorial`, `chat-neon`, `chat-soft`).

## Public APIs / Interfaces / Types (explicit changes)
- Added admin endpoints:
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`
- `POST /admin/apps/{app_id}/builder/draft-dev/session/ensure`
- `PATCH /admin/apps/{app_id}/builder/draft-dev/session/sync`
- `POST /admin/apps/{app_id}/builder/draft-dev/session/heartbeat`
- `GET /admin/apps/{app_id}/builder/draft-dev/session`
- `DELETE /admin/apps/{app_id}/builder/draft-dev/session`
- `GET /admin/apps/{app_id}/publish/jobs/{job_id}`
- Added public endpoints:
- `GET /public/apps/{slug}/runtime`
- `GET /public/apps/preview/revisions/{revision_id}/runtime`
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`
- Changed behavior:
- `GET /public/apps/{slug}/ui` always returns `410 UI_SOURCE_MODE_REMOVED`.
- `POST /admin/apps/{id}/publish` returns publish job metadata (`queued|running|succeeded|failed`) and accepts optional autosave payload.
- Type updates in frontend service types:
- draft-dev session fields + publish-job status fields.

## Security and Governance
- Build worker isolation:
- dedicated Node-capable worker image
- temp build dir per job
- no persistent project containers
- explicit job timeout + CPU/memory limits
- no host filesystem mounts
- restricted egress policy for build workers.
- Dependency governance:
- curated allowlist + pinned versions
- no arbitrary package install from chat.
- Draft preview security:
- backend proxy with preview-token validation.
- Static runtime security:
- strict CSP for static host.
- API calls through same-origin gateway path `/api/py`.
- tenant/app scoping unchanged in backend auth validators.

## Tests and Scenarios

## Backend tests
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/published_apps/`:
- create app seeds full Vite file baseline.
- builder revision save does not enqueue heavy draft build.
- unsupported package in `package.json` fails validation.
- build success writes `dist_manifest` + storage prefix.
- stale build completion (older `build_seq`) is discarded and does not overwrite newer status/artifacts.
- publish enqueues async full-build job and tracks lifecycle (`queued/running/succeeded/failed`).
- publish failure leaves existing published revision pointer unchanged.
- public runtime descriptor returns `vite_static` + `published_url`.
- `/ui` always returns `410 UI_SOURCE_MODE_REMOVED`.
- preview token allows draft asset proxy; invalid token rejected.
- Update `test_state.md` with new command/date/result.
Status:
- Core published-app backend tests currently pass (latest targeted run includes async publish job flow, draft-dev-aware builder behavior, runtime descriptor, and preview assets).

## Worker/service tests
- Task unit tests for subprocess/npm failure handling.
- storage upload and manifest generation tests (mock boto3).
- publish job failure leaves prior published revision pointer unchanged.
- Vite asset base/path test ensures built chunks resolve under nested `{slug}/{revision_id}/` URL and preview proxy URL.
Status:
- Pending dedicated worker/service unit tests for real npm build execution and storage upload pipeline.

## Frontend tests
- builder preview shows build pending/running/failure/success transitions.
- published page redirects to `published_url` when published.
- remove compileReactArtifact dependency in published runtime tests.
Status:
- Builder workspace preview/build-status tests updated for runtime descriptor flow.
- Published runtime redirect tests updated for static-only runtime resolution behavior.

## End-to-end acceptance
- create app -> edit -> draft dev sandbox preview works with HMR path.
- publish -> async full clean build -> URL points to runtime revision.
- static app loads and can call shared backend chat/auth via `/api/py`.
- verify `/public/apps/{slug}/ui` consistently returns `410 UI_SOURCE_MODE_REMOVED`.
Status:
- Verified locally against live app/revision (`f6aae6d2-39b0-4fe7-81c3-43ce409f2270` / `4dbde79d-699d-4ab3-861f-dc56238995d6`): rebuild succeeded, runtime preview URL resolved to `/public/apps/.../assets/index.html?preview_token=...`, iframe-style load returned `200`, and JS asset follow-up returned `200`.

## Documentation updates required
- Update `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/Plans/AppsBuilderV1Plan.md`.
- Update `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/Apps.md`.
- Update `/Users/danielbenassaya/Code/personal/talmudpedia/code_architect/architecture_tree.md` for new template/worker/storage modules and directories.
- Update relevant test-state files in `backend/tests/published_apps/` and frontend published-app test state.
- Ensure every edited `.md` includes `Last Updated: 2026-02-14`.

## Documentation contradiction alert
- Current compile-policy section in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/Plans/AppsBuilderV1Plan.md` (React-only import allowlist) conflicts with this approved Option A architecture (full Vite project + curated semi-open deps). This must be explicitly replaced, not appended.

## Assumptions and defaults
- Package manager is npm (`package-lock.json`) for build workers.
- Object storage is S3-compatible and CDN sits in front of storage paths.
- API gateway can route `/api/py` on app runtime domains to backend.
- Big-bang means static runtime is canonical and source-UI path remains removed.
- Existing template keys remain unchanged; only implementation source changes.
