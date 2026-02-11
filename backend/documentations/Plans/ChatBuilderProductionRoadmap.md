# ChatBuilder Production Roadmap (Lovable/Base44 Parity Target)

Last Updated: 2026-02-11

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
1. Ship Phase 0 completely (policy + compile gate + tests).
2. Start Phase 1 with model-backed patch generation behind a feature flag.
3. Build a 25-task benchmark pack for weekly evaluation before wider rollout.

## Dependency Notes
1. Reuse existing platform strengths:
- Agent execution/streaming infrastructure and tool runtime patterns.
2. Keep builder-specific safety policy stricter than general runtime until benchmark stability is proven.

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

### Completed (Phase 2 - Initial Continuation)
1. Agentic tool primitives added behind feature flag:
- Flag: `BUILDER_AGENTIC_LOOP_ENABLED`.
- `list_files`, `read_file`, `search_code`, `apply_patch_dry_run`, `compile_project`, `run_targeted_tests`.

2. Bounded iterative loop added:
- Iterative patch generation + dry-run + compile checks with bounded retries/iterations.

3. UI transparency path started:
- Stream includes structured tool/status events for chat timeline rendering.

### Validation Results
1. `pytest backend/tests/published_apps/test_builder_revisions.py -q`
- PASS (7 passed)

2. `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps/apps_builder_workspace.test.tsx`
- PASS (3 tests)

### In Progress
1. Builder conversation persistence for replay/audit (Phase 1 item 4) is still pending.
2. Phase 2 loop currently uses lightweight project tools and no external test execution; deeper tool autonomy/evals are pending.
