# Coding-Agent Hardening + Cursor-Style Per-Run Model Selection

Last Updated: 2026-02-18

## Implementation Status (as of 2026-02-18)
- Phase 1 (Must-Ship): **Implemented and finished**.
- Phase 2 (Remaining gaps): **Not finished** (planned follow-up work remains).

### Implemented/Finished
- Public API contract updates for run-level model selection (`model_id`, `requested_model_id`, `resolved_model_id`).
- Run-level model pinning persistence and execution-time model override.
- Builder per-run model picker (`Auto` + active chat models) with per-message selection.
- Fail-fast unavailable model contract (`400 CODING_AGENT_MODEL_UNAVAILABLE`).
- Coding-agent required-field validation (`TOOL_INPUT_VALIDATION_FAILED`) before dispatch.
- Tool/policy error normalization and deterministic diagnostics mapping for `tool.failed`.
- Run creation resilience hardening: draft runtime prewarm failures are treated as best-effort (warn + continue) so run creation is not blocked by local runtime bootstrap errors.
- Phase 1 backend/frontend regression coverage (including model selection and validation failure paths).

### Remaining (Not Yet Finished)
- Phase 2.1 deeper runtime/event assertions.
- Phase 2.2 tool output and cancellation hardening.
- Phase 2.3 DB-backed durability checkpointer for multi-instance readiness.
- Phase 2.4 visual/browser E2E coverage for builder coding-agent/model-picker flows.

## Summary
Implement a two-phase delivery that closes the high-risk coding-agent gaps first and introduces direct model selection per message/run (Cursor-style), then completes the remaining hardening/testing gaps.

This plan is aligned to chosen decisions:
- Model selection is per run (user can change before each sent message).
- Picker includes `Auto` + explicit model options.
- `Auto` keeps current tenant/global default behavior.
- Model picker shows active chat models only.
- If selected model is unavailable at send time, fail fast with `400`.
- Strict required-field validation is enforced for coding-agent tools first.
- Delivery strategy is two-phase hardening.

## Public API / Interface Changes
- Extend `POST /admin/apps/{app_id}/coding-agent/runs` request schema in `backend/app/api/routers/published_apps_admin_routes_coding_agent.py` with optional `model_id: UUID | null`.
- Extend run response payload (`CodingAgentRunResponse`) with `requested_model_id` and `resolved_model_id` so run history is auditable.
- Add deterministic model-validation error contract for run creation:
  - `400` with `detail = { code: "CODING_AGENT_MODEL_UNAVAILABLE", field: "model_id", message: "..." }`.
- Keep backward compatibility: if `model_id` is missing or `null`, behavior remains `Auto` (tenant default → global default → first active chat model).
- Frontend `publishedAppsService.createCodingAgentRun` payload in `frontend-reshet/src/services/published-apps.ts` is extended to include optional `model_id`.

## Phase 1 (Must-Ship): Model Selection + High-Risk Correctness

## 1. Model Selection Architecture (no shared-profile race conditions)
- Add run-level model pinning fields on `agent_runs` via Alembic migration: `requested_model_id`, `resolved_model_id` (FK to `model_registry.id`, nullable).
- Update `AgentRun` ORM in `backend/app/db/postgres/models/agents.py` with the two fields.
- In `backend/app/services/published_app_coding_agent_runtime.py`, resolve model at create-run time:
  - `model_id` provided → validate tenant/global visibility, `capability_type=chat`, `is_active=true`.
  - `model_id` missing/null → resolve using existing auto chain.
- Persist both `requested_model_id` and `resolved_model_id` on the run row.
- Keep coding-agent profile as a stable template; do not mutate shared agent profile per run for model changes.
- Apply resolved model at execution compile-time through run-scoped override in `backend/app/agent/execution/service.py` so each run executes with its pinned model regardless of later default changes.

## 2. Cursor-Style Per-Run Model Picker in Builder
- In `frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx`, add model state for composer (`null` = Auto).
- Load active chat models from `/models` using existing `modelsService`.
- Add compact selector in composer footer near submit button:
  - Display current selection label (`Auto` or model name).
  - Searchable dropdown/list (reuse existing model-selector primitives from `frontend-reshet/src/components/ai-elements/model-selector.tsx`).
- On submit, send selected `model_id` in create-run payload for that message/run.
- Keep UX “per run”: user can change selection before each message; no backend persistence beyond each run record.

## 3. Strict Tool Input Validation (coding-agent tools first)
- Add pre-dispatch required-field validation for coding-agent tool functions (`coding_agent_*`) before function execution.
- Validation source is tool schema `input.required`; enforce non-empty semantics for string required fields.
- When missing required fields, return structured failure payload (not generic policy error text), e.g.:
  - `{ error: "Missing required fields: path", code: "TOOL_INPUT_VALIDATION_FAILED", fields: ["path"] }`.
- Ensure this validation executes before path normalization/policy checks to eliminate intermittent `File path is required` from malformed tool-call shapes.

## 4. Error Semantics and Diagnostics Normalization
- Normalize builder policy exceptions into stable tool-failure envelopes with machine-readable `code/message/field`.
- Ensure SSE tool failure events include deterministic diagnostics for frontend rendering.
- Keep policy errors for true policy violations (blocked path, unsupported extension), but separate them from contract-validation errors.

## 5. Regression and Contract Tests (Phase 1)
- Backend tests in feature-grouped roots:
  - `backend/tests/coding_agent_api/`
  - `backend/tests/tool_execution/`
- Add/extend scenarios:
  - create run with `Auto`.
  - create run with explicit valid `model_id`.
  - create run with invalid/inactive/cross-tenant `model_id` → `400 CODING_AGENT_MODEL_UNAVAILABLE`.
  - run uses pinned `resolved_model_id` even if tenant defaults change after run creation.
  - coding-agent write/read/delete/rename missing required args fail with `TOOL_INPUT_VALIDATION_FAILED`.
  - policy violations still fail with policy code and field.
- Frontend tests:
  - `frontend-reshet/src/__tests__/published_apps/`
  - model selector renders options + Auto.
  - create-run payload includes selected `model_id`.
  - changing model between messages changes next run payload.
  - invalid selected model response displays actionable error.

## Phase 2 (Complete Remaining Gaps)

## 1. Deeper Runtime/Event Assertions
- Expand deterministic SSE envelope assertions beyond headers/generator execution.
- Add richer assertions for `tool.failed` payload semantics and diagnostics mapping in UI tests.

## 2. Tool Output and Cancellation Hardening
- Standardize tool output envelope shape across success/failure paths.
- Improve cancellation propagation and interruption handling in tool execution loops.

## 3. Durability and Multi-Instance Readiness
- Plan and implement DB-backed durable checkpointer replacement for current file-backed saver.
- Add migration/ops notes and fallback strategy for checkpointer cutover.

## 4. Visual E2E Coverage
- Add browser-level E2E for builder coding-agent panel and model picker interaction paths.
- Cover run stream rendering, selector switching, and failure UX.

## Test Plan and Acceptance Criteria
- Acceptance: user can select model per message, run executes with pinned model, and run records show requested/resolved model IDs.
- Acceptance: malformed coding-agent tool calls fail early with explicit missing-field diagnostics, not intermittent raw `File path is required`.
- Acceptance: policy violations remain explicit and distinct from contract validation errors.
- Acceptance: existing clients without `model_id` continue working unchanged under Auto behavior.
- Acceptance: all touched backend/frontend test suites pass and new feature test-state docs are updated.

## Documentation and Tracking Updates
- Update `backend/documentations/Plans/CodingAgentRuntimeRefactorImplementationTracker.md` with phase split and model-selection contract.
- Update relevant test state files with command/date/result and new scenarios:
  - `backend/tests/coding_agent_api/test_state.md`
  - `frontend-reshet/src/__tests__/published_apps/test_state.md`
- Keep `Last Updated` dates on edited markdown files.

## Assumptions and Defaults Locked
- Selection behavior: per run/message.
- Picker scope: active chat models only (tenant + global visibility).
- Auto semantics: existing default chain remains unchanged.
- Invalid selected model: fail fast `400`, no silent fallback.
- Validation hardening scope in phase 1: coding-agent tools only.
- Rollout strategy: two-phase (must-ship correctness first, deep hardening second).
