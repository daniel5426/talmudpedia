# Base44-Style Option A Implementation Plan (Vite Static Apps + Shared Backend)

Last Updated: 2026-02-11

## Summary
Move Apps Builder from “virtual React files compiled in-browser” to “full Vite React projects built by backend workers and deployed as static assets,” with big-bang runtime migration.

## Implementation Status Snapshot (as of 2026-02-11)
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
- `/public/apps/{slug}/ui` runtime-mode behavior (`legacy` payload, `static` -> `410 UI_SOURCE_MODE_REMOVED`).
- Publish artifact promotion wiring via storage service with `BUILD_ARTIFACT_COPY_FAILED` failure contract.
- Queue wiring for `apps_build` and placeholder `build_published_app_revision_task` lifecycle handling.
- Frontend service contracts for runtime/build status endpoints.
- Builder preview switched from in-browser compile to runtime URL + build-status polling in apps builder workspace.

Partially implemented:
- Worker task exists and updates lifecycle, but real isolated `npm ci`/`npm run build` + dist upload is still pending.
- Publish build-status gate (`BUILD_PENDING` / `BUILD_FAILED`) is currently feature-flagged (`APPS_BUILDER_PUBLISH_BUILD_GUARD_ENABLED`) instead of always-on.
- Published runtime route now performs runtime descriptor lookup and redirects to static `published_url`, while keeping legacy auth/chat fallback when runtime URL is unavailable.

Pending:
- End-to-end static artifact production pipeline (real build execution, dist manifest generation, object upload).
- Migration/backfill script for existing revisions and big-bang cutover execution.
- Worker hard-isolation controls (resource/egress/container hardening) and dedicated Node worker image rollout.

Locked choices:
- Build engine: Celery queue + dedicated Node build worker image.
- Asset storage/serving: object storage + CDN.
- Dependency policy: curated semi-open package set.
- Build trigger: auto on save; publish never rebuilds (publish promotes latest successful draft artifact).
- Draft access: backend proxy with preview token.
- Rollout: big-bang switch.
- Published URL shape: CDN path per revision.
- API origin: same-origin gateway (`/api/py` proxied on app domain).
- Template source: filesystem template packs.
- Artifact identity: immutable build outputs tied to source revision build; publish copies/promotes artifacts to published revision prefix.
- Vite asset base: relative paths (`base: "./"`) so nested CDN/proxy paths resolve chunks correctly.
- Build queue semantics: one active build per app; stale worker completions ignored via monotonic `build_seq`.

## Current-State Grounding (from repo)
- Builder policy now enforces Vite project + curated dependency rules in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin.py`.
- Builder preview now uses preview runtime descriptor + asset URL polling flow in `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx`.
- Published runtime page now performs runtime-based redirect first in `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/published/[appSlug]/page.tsx`, with legacy auth/chat UI kept as fallback.
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
- Task exists and handles lifecycle placeholders, but real build/upload flow and worker runtime image deployment are not completed yet.

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
- Publish flow for `build_status=succeeded`:
- clone draft -> new immutable published revision row
- copy dist objects from draft `dist_storage_prefix` to published revision prefix (`.../revisions/{published_revision_id}/dist/...`) without rebuild
- persist copied `dist_storage_prefix` + `dist_manifest` on published revision, then write `published_url`
- if artifact copy fails, publish fails with `500 BUILD_ARTIFACT_COPY_FAILED` and app remains on previous published revision.
Current gap:
- Full CDN published URL contract is not final yet (`_build_published_url` still drives runtime URL in current admin router).

## 6) Admin API contract updates
Status: Implemented with one flagged behavior.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin.py`:
- Update builder revision create/reset flows to:
- create revision with `build_status=queued`
- increment `build_seq`
- enqueue build task immediately
- return revision including build fields.
- Add build status endpoint:
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
- Add retry endpoint:
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`
- Update publish endpoint behavior:
- If current draft build status `queued|running` -> `409` with code `BUILD_PENDING`.
- If `failed` -> `422` with code `BUILD_FAILED` + diagnostics.
- If `succeeded` -> clone to published revision, copy/promote built artifacts to published revision prefix, set `published_url` (no rebuild during publish).
- Remove React-only import allowlist enforcement in project validator.
- Replace with Vite project + dependency policy validation.
Note:
- Publish build gate is currently behind `APPS_BUILDER_PUBLISH_BUILD_GUARD_ENABLED`.

## 7) Public runtime API contract updates
Status: Implemented.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_public.py`:
- Add runtime descriptor endpoint:
- `GET /public/apps/{slug}/runtime`
- Response fields:
- `app_id`, `slug`, `revision_id`, `runtime_mode: "vite_static"`, `published_url`, `asset_base_url`, `api_base_path: "/api/py"`.
- Keep `/public/apps/{slug}/config` for auth/status metadata.
- `/public/apps/{slug}/ui` behavior by runtime mode:
- `APPS_RUNTIME_MODE=legacy`: keep existing UI-source response for rollback compatibility.
- `APPS_RUNTIME_MODE=static`: return `410 UI_SOURCE_MODE_REMOVED`.
- Add draft preview asset proxy endpoint:
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`
- Requires preview token principal validation, then streams object storage asset.
- Add preview runtime descriptor endpoint:
- `GET /public/apps/preview/revisions/{revision_id}/runtime`
- Returns `preview_url` pointing to proxy asset base.

## 8) Frontend changes
Status: Partially implemented.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/published-apps.ts`:
- extend `PublishedAppRevision` with build fields.
- add calls for build status/retry endpoints.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/preview/PreviewCanvas.tsx`:
- remove `compileReactArtifactProject` path for app-builder preview.
- iframe should load preview asset URL from backend runtime descriptor.
- show build statuses: `queued/running/succeeded/failed`.
- poll build status while pending.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/published-runtime.ts`:
- add `getRuntime()` endpoint.
- remove reliance on UI source files for public runtime.
- In `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/published/[appSlug]/page.tsx`:
- big-bang: replace client compile path with redirect flow:
- fetch config/runtime
- if published + runtime available -> `window.location.replace(published_url)`
- keep auth gating routes only as fallback until static app auth UI is fully migrated.
Current gap:
- Legacy auth/chat fallback still exists in the published route and should be removed once static app auth UX is fully migrated.

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
- Feature flag `APPS_RUNTIME_MODE=legacy|static`.
- keep legacy code path available until migration completion verification, then remove.

## Public APIs / Interfaces / Types (explicit changes)
- Added admin endpoints:
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`
- Added public endpoints:
- `GET /public/apps/{slug}/runtime`
- `GET /public/apps/preview/revisions/{revision_id}/runtime`
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`
- Changed behavior:
- `GET /public/apps/{slug}/ui`:
- `legacy` mode -> existing source-UI payload.
- `static` mode -> `410 UI_SOURCE_MODE_REMOVED`.
- `POST /admin/apps/{id}/publish` may return:
- `409 BUILD_PENDING`
- `422 BUILD_FAILED`
- `500 BUILD_ARTIFACT_COPY_FAILED`
- Type updates in frontend service types:
- revision build fields + runtime descriptor types.

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
- builder revision save queues build.
- unsupported package in `package.json` fails validation.
- build success writes `dist_manifest` + storage prefix.
- stale build completion (older `build_seq`) is discarded and does not overwrite newer status/artifacts.
- publish blocked on `BUILD_PENDING` and `BUILD_FAILED`.
- publish artifact promotion copies draft dist to published revision prefix (no rebuild).
- public runtime descriptor returns `vite_static` + `published_url`.
- `/ui` serves legacy payload when `APPS_RUNTIME_MODE=legacy`, returns 410 when `APPS_RUNTIME_MODE=static`.
- preview token allows draft asset proxy; invalid token rejected.
- Update `test_state.md` with new command/date/result.
Status:
- Core published-app backend tests currently pass (latest targeted run includes build endpoints, runtime descriptor, preview assets, and publish copy-failure contract).

## Worker/service tests
- Task unit tests for subprocess/npm failure handling.
- storage upload and manifest generation tests (mock boto3).
- artifact-copy failure during publish returns `BUILD_ARTIFACT_COPY_FAILED` and leaves prior published revision unchanged.
- Vite asset base/path test ensures built chunks resolve under nested `{slug}/{revision_id}/` URL and preview proxy URL.
Status:
- Pending dedicated worker/service unit tests for real npm build execution and storage upload pipeline.

## Frontend tests
- builder preview shows build pending/running/failure/success transitions.
- published page redirects to `published_url` when published.
- remove compileReactArtifact dependency in published runtime tests.
Status:
- Builder workspace preview/build-status tests updated for runtime descriptor flow.
- Published runtime redirect migration tests are still pending with the page migration.

## End-to-end acceptance
- create app -> edit -> auto-build -> preview works.
- publish -> URL points to CDN path with revision id.
- static app loads and can call shared backend chat/auth via `/api/py`.
- rollback check: flip `APPS_RUNTIME_MODE=legacy` and verify old `/ui` runtime path remains functional.

## Documentation updates required
- Update `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/Plans/AppsBuilderV1Plan.md`.
- Update `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/Apps.md`.
- Update `/Users/danielbenassaya/Code/personal/talmudpedia/code_architect/architecture_tree.md` for new template/worker/storage modules and directories.
- Update relevant test-state files in `backend/tests/published_apps/` and frontend published-app test state.
- Ensure every edited `.md` includes `Last Updated: 2026-02-11`.

## Documentation contradiction alert
- Current compile-policy section in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/Plans/AppsBuilderV1Plan.md` (React-only import allowlist) conflicts with this approved Option A architecture (full Vite project + curated semi-open deps). This must be explicitly replaced, not appended.

## Assumptions and defaults
- Package manager is npm (`package-lock.json`) for build workers.
- Object storage is S3-compatible and CDN sits in front of storage paths.
- API gateway can route `/api/py` on app runtime domains to backend.
- Big-bang means static runtime is default after migration; legacy source-UI path is retained only behind `APPS_RUNTIME_MODE=legacy` rollback flag until final removal.
- Existing template keys remain unchanged; only implementation source changes.
