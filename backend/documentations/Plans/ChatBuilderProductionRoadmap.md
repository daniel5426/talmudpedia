# ChatBuilder Production Roadmap (Lovable/Base44 Parity Target)

Last Updated: 2026-02-12

## Goal
Upgrade the Apps Builder `Builder Chat` from a v1 patch-demo flow into a production-grade AI coding assistant with reliability, autonomy, and UX quality comparable to Lovable/Base44 class products, aligned with the platform move to full backend-built Vite projects deployed as static assets.

## Scope
- In scope: `builder/chat/stream`, patch generation/apply/validation flow, builder chat UX, revision reliability, coding-agent tool loop, safety/policy, observability, quality gates, and integration with backend worker build/deploy flows for Vite projects.
- Out of scope for this track: billing, custom domains, and runtime end-user chat capability changes.

## Migration Directive (Big-Bang Runtime Refactor)
1. Runtime migration mode is **big-bang**, not dual-track:
- No long-lived support for the old "virtual React files compiled in-browser" runtime.
- AI coder behavior, validations, and tools must target backend worker builds for Vite projects as the source of truth.

2. Project shape assumptions are now full project-level:
- Not just `src/` patches; include project root artifacts as needed (`package.json`, `vite.config.*`, `index.html`, lockfiles, config/test files) under policy.
- Compile validity means backend worker `vite build` (or equivalent worker build contract), not heuristic import checks alone.

3. Agent loop success criteria are migration-aware:
- A "successful" turn requires worker build pass and deployable static asset output readiness.

## Canonical API Contract Map (Option A, 1:1)
1. Admin builder endpoints:
- `POST /admin/apps/{app_id}/builder/revisions`:
  - creates revision with `build_status=queued`,
  - enqueues worker build,
  - returns revision including build lifecycle fields.
- `POST /admin/apps/{app_id}/builder/template-reset`:
  - creates revision from filesystem template pack baseline,
  - sets `build_status=queued`,
  - enqueues worker build.
- `GET /admin/apps/{app_id}/builder/revisions/{revision_id}/build`:
  - returns build lifecycle state and diagnostics for a specific revision.
- `POST /admin/apps/{app_id}/builder/revisions/{revision_id}/build/retry`:
  - re-enqueues build for failed or retriable revision.

2. Publish gate contract:
- `POST /admin/apps/{id}/publish` must return:
  - `409` with `code: BUILD_PENDING` when draft build is `queued|running`,
  - `422` with `code: BUILD_FAILED` + diagnostics when draft build is `failed`,
  - success only when draft build is `succeeded`.

3. Public runtime endpoints:
- `GET /public/apps/{slug}/runtime`:
  - response includes `app_id`, `slug`, `revision_id`, `runtime_mode: \"vite_static\"`, `published_url`, `api_base_path: \"/api/py\"`.
- `GET /public/apps/preview/revisions/{revision_id}/runtime`:
  - preview runtime descriptor with preview URL base.
- `GET /public/apps/preview/revisions/{revision_id}/assets/{asset_path:path}`:
  - preview asset proxy; preview token required.

4. Public source-UI deprecation:
- `GET /public/apps/{slug}/ui` returns `410` with `code: UI_SOURCE_MODE_REMOVED` after big-bang cutover.

5. Revision schema contract additions:
- `build_status`: `queued|running|succeeded|failed`,
- `build_error`, `build_started_at`, `build_finished_at`,
- `dist_storage_prefix`, `dist_manifest`,
- `template_runtime` (default `vite_static`).

6. Build worker contract:
- Celery queue: `apps_build`.
- Task contract: `build_published_app_revision_task(revision_id, tenant_id, app_id, slug, build_kind)`.
- Build flow contract:
  - load revision files from DB,
  - validate Vite project + curated dependency policy,
  - materialize temp project,
  - run `npm ci` + `npm run build`,
  - normalize `dist_manifest`,
  - upload dist assets under deterministic prefix:
    - `apps/{tenant_id}/{app_id}/revisions/{revision_id}/dist/...`,
  - update revision build status/diagnostics.

7. Dependency and project policy contract:
- `package.json` required at project root.
- Bare imports must be declared in `dependencies`/`devDependencies`.
- Declared packages/versions must match curated pinned catalog.
- URL imports and absolute filesystem imports forbidden.
- Allowed/managed Vite project paths include:
  - `index.html`, `package.json`, `vite.config.ts`, `tsconfig*.json`, `postcss.config.*`, `tailwind.config.*`, `src/**`, `public/**`.

8. URL and storage contract:
- `published_url = {APPS_CDN_BASE_URL}{APPS_CDN_PUBLIC_PREFIX}/{slug}/{revision_id}/`.
- Required env contracts:
  - `APPS_BUNDLE_BUCKET`,
  - `APPS_BUNDLE_REGION`,
  - `APPS_BUNDLE_ENDPOINT`,
  - `APPS_BUNDLE_ACCESS_KEY`,
  - `APPS_BUNDLE_SECRET_KEY`,
  - `APPS_CDN_BASE_URL`,
  - `APPS_CDN_PUBLIC_PREFIX` (default `/apps`).

## Current State (Code-Verified)
1. Builder workspace and stream contract are implemented.
- `frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx`
- `backend/app/api/routers/published_apps_admin.py`

2. Chat patch generation now supports a feature-flagged model path, with heuristic fallback.
- Default-off flag: `BUILDER_MODEL_PATCH_GENERATION_ENABLED`.
- Fallback path still uses `_build_builder_patch_from_prompt(...)`.
- `backend/app/api/routers/published_apps_admin.py`

3. Patch validation has Phase-0 guardrails in place.
- Path normalization and traversal blocking.
- Allowed roots/extensions policy.
- Operation count and project/file size limits.
- Import policy checks and unresolved local import diagnostics.

4. Server-side compile-style validation now gates revision persistence.
- `POST /admin/apps/{app_id}/builder/revisions` now rejects invalid projects before save.
- `POST /admin/apps/{app_id}/builder/validate` supports dry-run validation + diagnostics.
- Note: this is still policy/import validation, not yet worker-executed `vite build`.

5. Test coverage validates contracts and happy paths, not production agent quality.
- `backend/tests/published_apps/test_builder_revisions.py`
- `frontend-reshet/src/__tests__/published_apps/apps_builder_workspace.test.tsx`

6. Security baseline exists and is a strength.
- Revision conflict contract (`REVISION_CONFLICT`), preview-token model, published snapshot isolation.

7. Template pack loading now excludes generated build/vendor artifacts.
- Loader ignores `node_modules`, `dist`, and generated config/build artifacts so builder validation operates on policy-managed project source only.
- `backend/app/services/published_app_templates.py`

8. Build enqueue is now resilient when worker infrastructure is unavailable.
- Revision creation/reset still succeeds if Celery/Redis enqueue fails at request time; enqueue failure is logged instead of failing admin APIs.
- `backend/app/api/routers/published_apps_admin.py`

9. Builder policy now supports wider Vite root-level workflow files.
- Allowed builder-managed root paths now include common lockfiles and test/lint/format/build configs (e.g., `pnpm-lock.yaml`, `yarn.lock`, `vite.config.*`, `vitest.config.*`, `eslint/prettier/jest/playwright` config families).
- Import/dependency validation now treats `.mts`/`.cts` files as code files for dependency and local-import diagnostics.
- `backend/app/api/routers/published_apps_admin.py`
- `backend/app/services/apps_builder_dependency_policy.py`

## Parity Bar (What "Lovable/Base44-Level" Means Here)
1. Reliable multi-turn coding agent that reads codebase context before editing and can recover from compile/runtime failures.
2. Tool-augmented edit loop (search/read/edit/compile/test) with deterministic guardrails.
3. Strong UX for patch review (diffs, accept/reject, undo/restore, version history).
4. Integration-ready workflow (git export/sync path, deploy-ready previews, secrets-safe integrations).
5. Production observability + evaluation framework (quality and latency SLOs, regression suite).

## Gap Summary
1. Agent intelligence gap: static rule-based patch generator vs model-driven planner/coder loop.
2. Migration gap: current validation and tool loop are still optimized for virtual-file heuristics, not full worker build/deploy execution for Vite projects.
3. UX gap: no first-class patch review workflow (diff accept/reject, staged apply, rollback labels).
4. Ops gap: no systematic quality metrics/evals for coding success, regression, or latency.

## Roadmap

### Phase 0 - Reliability + Safety Foundation (1 sprint)
1. Add backend patch policy layer:
- Normalize and validate paths.
- Restrict allowed file types/roots.
- Cap operations per request, per-file bytes, total bytes, and max file count.

2. Add server-side compile gate before revision persistence:
- Apply patch in-memory.
- Compile in isolated worker context.
- Persist revision only on successful compile.
- Return structured compile diagnostics on failure.

3. Strengthen API contracts:
- Add structured event envelopes (`stage`, `request_id`, `diagnostics`).
- Add typed error codes for policy denial and compile failure.

4. Tests:
- Negative tests for path traversal/oversized payload/invalid rename.
- Compile-fail path tests for both direct revision save and chat patch apply.

Exit criteria:
- No invalid patch can persist a revision.
- Every saved draft is compile-valid under the same backend rules.

### Phase 1 - Real Coding Model Core (2 sprints)
1. Replace `_build_builder_patch_from_prompt` with model-backed generation.
2. Introduce structured output contract:
- Model outputs `BuilderPatchOp[]` + rationale + assumptions.
- Strict schema validation with retry-on-invalid-output policy.

3. Add context builder:
- File tree snapshot.
- Relevant files selection (`entry_file`, imported neighbors, recently edited files, project root config/build files).
- Token-budgeted prompt packing.

4. Persist builder conversations:
- Store user prompts, assistant outputs, patch metadata, worker build/deploy diagnostics, and failure causes for replay/audit.

5. Adapt patch policy to full Vite project contracts:
- Expand allowed/managed paths beyond `src/` and `public/` where required for Vite projects.
- Add explicit policy for root-level build/config/dependency files.

Exit criteria:
- >70% first-pass success on internal benchmark tasks (worker-build-valid and request-aligned).

### Phase 2 - Tool-Augmented Agentic Loop (2-3 sprints)
1. Add builder-agent tools:
- `list_files`, `read_file`, `search_code`, `apply_patch_dry_run`, `compile_project`, `run_targeted_tests`, `build_project_worker`, `prepare_static_bundle`.

2. Implement bounded iterative loop:
- plan -> inspect -> patch -> install/build/test -> repair (max iterations + timeout + token caps).

3. UI transparency:
- Stream tool actions and statuses in chat timeline (readable, not raw trace noise).

Exit criteria:
- Agent can self-correct worker build failures in-loop for benchmark tasks without user re-prompting.

### Phase 2.5 - Big-Bang Runtime Migration Gate (1 sprint)
1. Replace compile-style draft gating with worker build gating for save/apply decisions.
2. Switch preview/runtime artifact source to backend-produced static assets only.
3. Remove legacy browser-compile runtime dependency paths from builder workflows.

Exit criteria:
- No builder save/publish path depends on in-browser virtual React compilation.
- All builder validation and preview handoff paths run through backend worker build contracts.

### Phase 3 - Review UX + Versioning Parity (2 sprints)
1. Diff-first patch review:
- Show patch by file with accept/reject per hunk or per file.

2. Revision ergonomics:
- Named checkpoints.
- One-click restore.
- Undo latest AI apply.

3. Better chat ergonomics:
- `@file` mentions.
- "Explain change" and "Revert this file" quick actions.

Exit criteria:
- Users can safely inspect and control AI edits before persistence/publish.

### Phase 4 - Integration + Delivery Parity (2 sprints)
1. Git workflow:
- Export patch set/commit payload.
- Optional branch+PR integration path.

2. Deployment readiness checks:
- Pre-publish health checks and blocking diagnostics.
- Environment/secret validation hooks.

3. Integration scaffolds:
- Guided setup templates for common backend services.

Exit criteria:
- Production handoff path is deterministic from builder revision to deploy artifact.

### Phase 5 - Quality System + SLOs (ongoing, initial 1 sprint setup)
1. Create benchmark suite (task corpus by difficulty and template).
2. Define and track KPIs:
- task success rate
- compile pass rate
- self-heal rate
- median TTFT
- p95 end-to-end edit completion
- rollback/revert rate

3. Add release gates:
- No rollout if KPI regression exceeds threshold.

Exit criteria:
- Agent quality is measured continuously and releases are gated by objective thresholds.

## Suggested First Execution Slice (Next 2 Weeks)
1. Keep Phase 0 contracts stable while widening policy/contracts for full Vite project files.
2. Promote Phase 1 model-backed generation as default for migration tenants behind feature flags.
3. Replace compile-style checks with worker `vite build` validation in the builder save/apply path.
4. Build a 25-task benchmark pack measured on worker build/deploy readiness (not browser compile pass).

## Dependency Notes
1. Reuse existing platform strengths:
- Agent execution/streaming infrastructure and tool runtime patterns.
2. Keep builder-specific safety policy stricter than general runtime until worker-build benchmark stability is proven.
3. Coordinate directly with backend worker/deploy pipeline owners so builder tool contracts use production artifact APIs.

## Implementation Status
### Completed (Phase 0 - Reliability + Safety Foundation)
1. Backend policy/validation layer added in `backend/app/api/routers/published_apps_admin.py`:
- `BUILDER_PATCH_POLICY_VIOLATION` error contract.
- Path/root/extension validation.
- Max operations/file count/file size/total size limits.
- Package import allowlist + network/absolute import deny rules.
- Local import resolution diagnostics.
- `rename_file` now rejects missing sources and existing targets.

2. Server-side compile-style validation gate wired to:
- `POST /admin/apps/{app_id}/builder/revisions`
- `POST /admin/apps/{app_id}/builder/chat/stream` (generated patch is validated before stream patch event)

3. Dry-run validation endpoint added:
- `POST /admin/apps/{app_id}/builder/validate`

4. Frontend service contract updated:
- `frontend-reshet/src/services/published-apps.ts`
- `frontend-reshet/src/services/index.ts`
- Added `BuilderValidationResponse` and `validateRevision(...)`.

5. Backend tests expanded:
- `backend/tests/published_apps/test_builder_revisions.py`
- Added coverage for path traversal rejection, unsupported package import rejection, validate-endpoint diagnostics, oversized payload rejection, and invalid rename rejection.

6. Stream contract upgraded:
- `POST /admin/apps/{app_id}/builder/chat/stream` events now include `stage` and `request_id`.
- Envelope supports optional `diagnostics` payloads and explicit `done` event shape.

### Completed (Phase 1 - Initial Start)
1. Model-backed structured patch generation added behind feature flag:
- Flag: `BUILDER_MODEL_PATCH_GENERATION_ENABLED`.
- Model output schema: `operations`, `summary`, `rationale`, `assumptions`.
- Strict schema validation + retry-on-invalid-output.
- Dry-run apply/compile validation before stream patch emission.

2. Context builder added for prompt packing:
- File tree snapshot.
- Relevant-file selection (`entry_file`, key app files, imported neighbors, recent paths, prompt-matched files).
- Per-file truncation for prompt budget control.

3. Builder conversation persistence and replay endpoint added:
- New table/model: `PublishedAppBuilderConversationTurn`.
- `POST /admin/apps/{app_id}/builder/chat/stream` now persists both success and failure turns (prompt, summary/rationale/assumptions, patch ops, tool trace, diagnostics, failure code).
- `GET /admin/apps/{app_id}/builder/conversations` returns newest-first persisted turns for replay/audit.

### Completed (Phase 2 - Initial Continuation)
1. Agentic tool primitives added behind feature flag:
- Flag: `BUILDER_AGENTIC_LOOP_ENABLED`.
- `list_files`, `read_file`, `search_code`, `apply_patch_dry_run`, `compile_project`, `run_targeted_tests`, `build_project_worker`, `prepare_static_bundle`.
- Current state:
  - `compile_project` remains compile-style validation.
  - `run_targeted_tests` now supports real execution behind `APPS_BUILDER_TARGETED_TESTS_ENABLED`.
  - Targeted test runner uses project scripts + discovered test files and returns `passed|failed|skipped` with diagnostics.
  - `build_project_worker` and `prepare_static_bundle` now run in-loop with structured tool trace events.
  - Worker build execution is controlled by `APPS_BUILDER_WORKER_BUILD_GATE_ENABLED` (`succeeded` when enabled and preflight passes, `skipped` when disabled).

2. Bounded iterative loop added:
- Iterative patch generation + dry-run + compile checks with bounded retries/iterations.

3. UI transparency path started:
- Stream includes structured tool/status events for chat timeline rendering.

4. Prompt file-focus support added for targeted multi-file edits.
- Agentic context selection now prioritizes prompt `@file` mentions.
- Loop inspect stage reads prompt-mentioned files through `read_file` tool events before generation.
- Mention resolver supports exact paths and unique basename matching.

5. Agentic loop failure semantics tightened.
- Loop no longer returns partial patch success when downstream gates fail repeatedly.
- On in-loop failures, tool trace events are propagated into persisted conversation failure rows for replay/debug (`run_targeted_tests`, `build_project_worker`, etc.).

### Completed (Phase 2.5 - Initial Start)
1. Publish gate contract added (always-on):
- `POST /admin/apps/{id}/publish` returns:
  - `409` with `code: BUILD_PENDING` when draft build status is `queued|running`,
  - `422` with `code: BUILD_FAILED` + diagnostics when draft build status is `failed`,
  - success when draft build status is `succeeded`.

2. Worker-build preflight gate added (feature-flagged) for draft save/apply validation:
- Flag: `APPS_BUILDER_WORKER_BUILD_GATE_ENABLED` (default off).
- When enabled:
  - `POST /admin/apps/{app_id}/builder/revisions` runs worker-style `npm install/npm ci` + `npm run build` preflight before persistence.
  - `POST /admin/apps/{app_id}/builder/validate` includes worker-style preflight in validation.
  - `POST /admin/apps/{app_id}/builder/chat/stream` blocks patch apply emission if worker-style preflight fails.

3. Queue-unavailable safety path added for builder build automation:
- `APPS_BUILDER_BUILD_AUTOMATION_ENABLED` may be enabled in runtime environments; enqueue failures no longer break synchronous admin API flows.
- Enqueue failures are downgraded to warnings with revision/app/build context for observability.

### Validation Results
1. `pytest backend/tests/published_apps/test_builder_revisions.py -q`
- PASS (17 passed)

2. `pytest backend/tests/published_apps/test_admin_apps_publish_rules.py backend/tests/published_apps/test_public_app_resolve_and_config.py -q`
- PASS (8 passed)

3. Test runtime stabilization for backend suites:
- Default pytest env now forces `APPS_BUILDER_BUILD_AUTOMATION_ENABLED=0` unless explicitly overridden, preventing Redis/Celery dependency leakage in local/in-memory test runs.
- `backend/tests/conftest.py`

### In Progress
1. Phase 2 loop now includes worker-build/static-bundle plus targeted-tests stages; remaining work is richer tool autonomy/evals and smarter test targeting heuristics.
2. Big-bang migration alignment is pending:
- Make worker-build preflight gate default-on after rollout hardening and latency budget confirmation.
- Expand patch policy to full Vite project file set and dependency-aware constraints.
- Ensure preview/runtime paths consume backend-produced static assets only.
3. Phase 2 agent loop still relies on compile-style checks for fast inner-loop validation (`compile_project`) ahead of worker build/test gates.
