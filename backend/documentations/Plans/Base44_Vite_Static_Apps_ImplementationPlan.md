# Base44-Style Option A Implementation Plan (Vite Static Apps + Shared Backend)

Last Updated: 2026-02-11

## Summary
Move Apps Builder from “virtual React files compiled in-browser” to “full Vite React projects built by backend workers and deployed as static assets,” with big-bang runtime migration.

Locked choices:
- Build engine: Celery queue + dedicated Node build worker image.
- Asset storage/serving: object storage + CDN.
- Dependency policy: curated semi-open package set.
- Build trigger: auto on save + publish.
- Draft access: backend proxy with preview token.
- Rollout: big-bang switch.
- Published URL shape: CDN path per revision.
- API origin: same-origin gateway (`/api/py` proxied on app domain).
- Template source: filesystem template packs.

## Current-State Grounding (from repo)
- Builder policy currently enforces React-only imports and `src/`/`public/` roots in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin.py`.
- Runtime currently client-compiles revision `files` in `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/published/[appSlug]/page.tsx`.
- Published UI API currently returns source files via `/public/apps/{slug}/ui` in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_public.py`.
- Celery + Redis already exist in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/workers/celery_app.py` and `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/workers/tasks.py`.

## Architecture Changes

## 1) Template System: filesystem Vite template packs
- Replace string-built template code in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_templates.py` with filesystem-backed packs.
- Add template pack root: `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/templates/published_apps/`.
- Add one folder per template key (`chat-classic`, `chat-editorial`, `chat-neon`, `chat-soft`, `chat-grid`), each containing a full Vite SPA project baseline.
- Add template manifest per pack (`template.manifest.json`) with metadata (`key`, `name`, `description`, `thumbnail`, `tags`, `entry_file`).
- Keep existing 5 keys unchanged for API compatibility.
- Keep shared backend runtime SDK in each template project as source code inside pack.

## 2) Revision model upgrade for static bundle lifecycle
- Add Alembic migration extending `published_app_revisions` in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/db/postgres/models/published_apps.py`.
- Add columns:
- `build_status` (`queued|running|succeeded|failed`, default `queued`)
- `build_error` (nullable text)
- `build_started_at` (nullable timestamp)
- `build_finished_at` (nullable timestamp)
- `dist_storage_prefix` (nullable string)
- `dist_manifest` (nullable JSONB; includes entry HTML + asset list + hashes)
- `template_runtime` (string, default `vite_static`)
- Keep existing `files` and `entry_file` as source-of-truth project files.
- Keep `compiled_bundle` as deprecated/unused field for migration compatibility, then remove in follow-up migration.

## 3) Curated semi-open dependency policy
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
- Add new Celery task in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/workers/tasks.py`:
- `build_published_app_revision_task(revision_id, tenant_id, app_id, slug, build_kind)`
- Task flow:
- Load revision files from DB.
- Validate project + dependency policy.
- Materialize project to temp dir.
- Run `npm ci` (with cached npm directory) + `npm run build`.
- Read `dist/`, produce normalized `dist_manifest`.
- Upload `dist/` to object storage under deterministic prefix:
- `apps/{tenant_id}/{app_id}/revisions/{revision_id}/dist/...`
- Update revision build columns to `succeeded`/`failed`.
- Add build queue routing in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/workers/celery_app.py`:
- queue `apps_build`.
- Add worker runtime image (new Dockerfile) with Python + Node LTS + npm for Celery worker pods/containers.

## 5) Object storage + CDN integration
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
- `published_url = {APPS_CDN_BASE_URL}{APPS_CDN_PUBLIC_PREFIX}/{slug}/{revision_id}/`
- `publish` writes this URL after successful build check.

## 6) Admin API contract updates
- In `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin.py`:
- Update builder revision create/reset flows to:
- create revision with `build_status=queued`
- enqueue build task immediately
- return revision including build fields.
- Add build status endpoint:
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
- Add retry endpoint:
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`
- Update publish endpoint behavior:
- If current draft build status `queued|running` -> `409` with code `BUILD_PENDING`.
- If `failed` -> `422` with code `BUILD_FAILED` + diagnostics.
- If `succeeded` -> clone to published revision including dist metadata and set `published_url`.
- Remove React-only import allowlist enforcement in project validator.
- Replace with Vite project + dependency policy validation.

## 7) Public runtime API contract updates
- In `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_public.py`:
- Add runtime descriptor endpoint:
- `GET /public/apps/{slug}/runtime`
- Response fields:
- `app_id`, `slug`, `revision_id`, `runtime_mode: "vite_static"`, `published_url`, `api_base_path: "/api/py"`.
- Keep `/public/apps/{slug}/config` for auth/status metadata.
- Deprecate `/public/apps/{slug}/ui` (big-bang):
- return `410` with migration detail code `UI_SOURCE_MODE_REMOVED`.
- Add draft preview asset proxy endpoint:
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`
- Requires preview token principal validation, then streams object storage asset.
- Add preview runtime descriptor endpoint:
- `GET /public/apps/preview/revisions/{revision_id}/runtime`
- Returns `preview_url` pointing to proxy asset base.

## 8) Frontend changes
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

## 9) Migration plan (big-bang)
- Add migration script/service:
- For all existing `published_app_revisions`:
- inject required Vite root files if missing.
- preserve existing `src/**` and `public/**`.
- ensure valid `package.json` with curated dependencies.
- mark revisions `build_status=queued`.
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
- `GET /public/apps/{slug}/ui` -> `410 UI_SOURCE_MODE_REMOVED`.
- `POST /admin/apps/{id}/publish` may return:
- `409 BUILD_PENDING`
- `422 BUILD_FAILED`
- Type updates in frontend service types:
- revision build fields + runtime descriptor types.

## Security and Governance
- Build worker isolation:
- dedicated Node-capable worker image
- temp build dir per job
- no persistent project containers.
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
- publish blocked on `BUILD_PENDING` and `BUILD_FAILED`.
- public runtime descriptor returns `vite_static` + `published_url`.
- `/ui` returns 410 after cutover.
- preview token allows draft asset proxy; invalid token rejected.
- Update `test_state.md` with new command/date/result.

## Worker/service tests
- Task unit tests for subprocess/npm failure handling.
- storage upload and manifest generation tests (mock boto3).

## Frontend tests
- builder preview shows build pending/running/failure/success transitions.
- published page redirects to `published_url` when published.
- remove compileReactArtifact dependency in published runtime tests.

## End-to-end acceptance
- create app -> edit -> auto-build -> preview works.
- publish -> URL points to CDN path with revision id.
- static app loads and can call shared backend chat/auth via `/api/py`.

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
- Big-bang means source-UI runtime mode is removed after migration flag flip.
- Existing template keys remain unchanged; only implementation source changes.
