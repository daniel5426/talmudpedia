# Apps Builder V1 (Vite Static Runtime, Big-Bang)
Last Updated: 2026-02-11

## Summary
This plan supersedes the older "virtual React files compiled in-browser" V1 assumptions.

V1 is now defined as:
- full Vite React project files stored per revision,
- backend worker builds,
- static asset deployment,
- runtime served from static bundles,
- big-bang migration away from source-UI runtime mode.

## Locked Architecture Decisions
1. Build engine: Celery + dedicated Node-capable build workers.
2. Asset serving: object storage + CDN.
3. Dependency policy: curated semi-open allowlist with pinned versions.
4. Build trigger: auto-build on save and publish checks.
5. Draft preview: backend proxy with preview token.
6. Rollout: big-bang runtime switch.
7. Runtime API origin on app domain: `/api/py` gateway path.
8. Template source: filesystem-backed full Vite template packs.

## Contract-First V1 Milestones

### Milestone 0: Runtime and Data Contract Lock
1. Runtime mode contract:
- `runtime_mode = "vite_static"` for published and preview descriptors.
- Source-UI runtime contract is deprecated and removed at cutover.

2. Revision lifecycle fields (required on revisions):
- `build_status`: `queued | running | succeeded | failed`
- `build_error`, `build_started_at`, `build_finished_at`
- `dist_storage_prefix`, `dist_manifest`
- `template_runtime` default: `vite_static`

3. Publish gate contract:
- `POST /admin/apps/{id}/publish` returns:
  - `409 BUILD_PENDING` when build is `queued|running`
  - `422 BUILD_FAILED` with diagnostics when build is `failed`
  - success only when build is `succeeded`

4. Public runtime contract:
- `GET /public/apps/{slug}/runtime` returns runtime descriptor.
- `GET /public/apps/{slug}/ui` returns `410 UI_SOURCE_MODE_REMOVED` after cutover.

### Milestone 1: Full Vite Template Packs + Revision Source Model
1. Replace string-generated templates with filesystem packs under:
- `backend/app/templates/published_apps/{template_key}/...`

2. Keep template keys API-stable:
- `chat-classic`, `chat-editorial`, `chat-neon`, `chat-soft`, `chat-grid`

3. Store full project source in revision files (including root build/config files as policy allows), not only `src/**` assumptions.

### Milestone 2: Dependency Policy + Build Queue Pipeline
1. Add dependency governance module:
- `backend/app/services/apps_builder_dependency_policy.py`

2. Enforce project/dependency rules:
- `package.json` required,
- bare imports must be declared,
- packages/versions must match curated allowlist pins,
- network URL imports and absolute filesystem imports forbidden.

3. Queue build task on revision save/reset and update build lifecycle fields.

4. Build flow contract:
- materialize project,
- `npm ci`, `npm run build`,
- upload `dist/` under deterministic prefix,
- persist manifest and status.

### Milestone 3: Admin and Public API Migration
1. Admin endpoints:
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`

2. Public endpoints:
- `GET /public/apps/{slug}/runtime`
- `GET /public/apps/preview/revisions/{revision_id}/runtime`
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`

3. Preview/published UI behavior:
- builder preview iframe loads runtime/asset descriptor URLs (no in-browser compile path),
- published page redirects to static published URL.

### Milestone 4: Big-Bang Migration and Legacy Removal
1. Migration/backfill:
- prepare existing revisions as valid Vite projects,
- queue builds for published first, then drafts.

2. Cutover condition:
- switch runtime mode after all currently published revisions succeed builds.

3. Failure handling:
- pause affected apps with actionable build errors.

4. Remove legacy source runtime path after completion verification.

## Public Interfaces / Types (V1 Target)
1. `PublishedAppRevision` includes build lifecycle and dist metadata fields.
2. Runtime descriptor types for published and preview runtime endpoints.
3. Publish error contracts:
- `BUILD_PENDING`
- `BUILD_FAILED`
4. Legacy source-UI contract deprecation code:
- `UI_SOURCE_MODE_REMOVED`

## Security and Governance
1. Build workers run in isolated temp directories per job.
2. Dependency installs constrained by curated allowlist policy.
3. Preview assets require valid preview token scoped to revision.
4. Static runtime calls backend through same-origin `/api/py` gateway.

## Implementation Status
### Completed
1. Draft/published revision architecture and optimistic concurrency contracts are in place.
2. Builder chat structured streaming and patch application contracts are in place.
3. Initial model-backed and agentic patch-generation framework is in place behind feature flags.

### In Progress
1. Worker-backed Vite build lifecycle on revision save/publish path.
2. Runtime descriptor/public static serving contracts and `/ui` cutover behavior.
3. Curated dependency governance module and full Vite root file policy.

### Deferred
1. Removal of deprecated `compiled_bundle` column in follow-up migration.
2. Legacy runtime path deletion until migration verification is complete.

## Validation Targets
1. Backend tests:
- build lifecycle transitions,
- publish gate codes,
- runtime descriptor responses,
- `/ui` deprecation response,
- preview asset auth.

2. Frontend tests:
- preview build status UX,
- runtime descriptor consumption,
- published static redirect.

3. End-to-end:
- create -> edit -> build -> preview -> publish -> static runtime load.

## Contradiction Resolution
This file intentionally replaces old React-only import allowlist and in-browser compile assumptions.
Any remaining docs that describe V1 as source-UI runtime should be treated as stale and updated to this contract.
