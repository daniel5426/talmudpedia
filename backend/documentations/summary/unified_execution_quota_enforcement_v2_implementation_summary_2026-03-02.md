# Unified Execution + Quota Enforcement V2 Implementation Summary

Last Updated: 2026-03-02

## Objective
Implement a reuse-first unification of non-coding agent execution on `AgentExecutorService`, enforce one V2 stream envelope across internal/public runtime surfaces, remove legacy workspace chat backend entrypoints, and add fast pre-run quota enforcement with reservation/counter settlement.

## Scope Implemented

### 1) Unified Execution Core (Reuse Existing Runtime)
- Kept `AgentExecutorService` as the single non-coding execution core.
- Reused existing `ExecutionEvent` + `StreamAdapter` pipeline and added a V2 stream contract mapper instead of building parallel event systems.
- Routed in-scope stream surfaces through shared execution orchestration with endpoint-level auth/context adapter differences.

### 2) Stream Contract Unification (Breaking V2)
- Added V2 envelope serializer/mapping:
  - `backend/app/agent/execution/stream_contract_v2.py`
- Applied V2 stream behavior to:
  - `POST /agents/{agent_id}/stream`
  - `POST /public/apps/preview/revisions/{revision_id}/chat/stream`
  - `POST /_talmudpedia/chat/stream` (via shared `_stream_chat_for_app`)
- Added runtime bootstrap contract marker:
  - `stream_contract_version: "run-stream.v2"`
- Added env-controlled enforcement path (`STREAM_V2_ENFORCED`, default enabled in code paths).

### 3) Usage Capture + Ledger Population
- Removed hardcoded `run.usage_tokens = 0` behavior in execution completion paths.
- Added usage extraction from event metadata with deterministic fallback estimation.
- Persisted total usage to `AgentRun.usage_tokens` for successful/finalized runs.

### 4) Quota Subsystem (Fast Pre-Run Enforcement)
- Added quota policy/counter/reservation model + migration:
  - `usage_quota_policies`
  - `usage_quota_counters`
  - `usage_quota_reservations`
- Added `UsageQuotaService` with:
  - pre-run reserve (`reserve_for_run`)
  - settlement (`settle_for_run`) with idempotency protection
  - release/expiry (`release_for_run`, `expire_stale_reservations`)
  - drift reconciliation (`reconcile_counter_from_ledger`)
- Integrated reserve-before-run-create behavior in `start_run`.
- Integrated settlement on completion and failure finalization.
- Integrated quota output cap propagation into runtime context (`quota_max_output_tokens`) and LLM invocation paths.

### 5) Quota Error API Behavior
- Standardized quota rejection payload to top-level 429 body for updated paths:
  - `{"code":"QUOTA_EXCEEDED", "scope_failures": [...], "period_start": ..., "period_end": ...}`
- Updated agents and published runtime stream startup paths to return JSON 429 payloads.

### 6) Legacy Chat Backend Removal (Internal Workspace)
- Removed legacy route mounting in `backend/main.py`:
  - `POST /chat` route mount removed
  - `/chats` route mount removed
- Path-mode published route remains removed as before (`/public/apps/{slug}/chat/stream` is not restored).

### 7) Stats/Admin Token Source Migration
- Switched admin monthly token reads to `AgentRun.usage_tokens` aggregation for user stats surfaces.
- `users.token_usage` is no longer used for authoritative enforcement/stats reads.

### 8) Quota Operations Background Tasks
- Added workers for operational consistency:
  - `expire_usage_quota_reservations_task`
  - `reconcile_usage_quota_counters_task`
- Added Celery routing and beat schedule entries with env controls:
  - `QUOTA_WORKERS_BEAT_ENABLED`
  - `QUOTA_EXPIRE_SWEEP_INTERVAL_SECONDS`
  - `QUOTA_RECONCILE_INTERVAL_SECONDS`

### 9) Frontend + Runtime SDK Compatibility
- Updated runtime SDK to require V2 bootstrap and V2 event envelopes.
- Updated frontend stream consumers to adapt V2 envelope to existing UI event handling.
- Redirected workspace chat routes to playground and deactivated legacy chat service behavior.

### 10) Run-Native Thread Unification (Hard Cut)
- Introduced run-native history persistence:
  - `agent_threads`
  - `agent_thread_turns`
  - `agent_runs.thread_id` linkage
- Unified request identity from `chat_id` to `thread_id` for non-coding execution surfaces:
  - `POST /agents/{agent_id}/stream`
  - `POST /agents/{agent_id}/run`
  - `POST /_talmudpedia/chat/stream`
  - `POST /public/apps/preview/revisions/{revision_id}/chat/stream`
- Unified stream response metadata:
  - `X-Chat-ID` replaced by `X-Thread-ID`
  - accepted events include `thread_id` in payload where applicable
- Runtime bootstrap now declares request contract:
  - `request_contract_version: "thread.v1"`
- Admin API hard rename:
  - `/admin/chats*` -> `/admin/threads*`
  - user stats `chats_count` -> `threads_count`
- Added host runtime history endpoints:
  - `GET /_talmudpedia/threads`
  - `GET /_talmudpedia/threads/{thread_id}`
- Runtime SDK breaking major update:
  - `RuntimeInput.chat_id` -> `RuntimeInput.thread_id`
  - `RuntimeStreamResult.chatId` -> `RuntimeStreamResult.threadId`
  - requires `request_contract_version === "thread.v1"`

## Important Migration Fixes Applied During Implementation

### A) Duplicate enum creation in Alembic migration
- Symptom during `alembic upgrade heads`: `DuplicateObject: type "usagequotascopetype" already exists`.
- Fix: changed migration enum definitions to PostgreSQL ENUM with `create_type=False` while keeping explicit `create(..., checkfirst=True)` in upgrade.

### B) Reservation schema run linkage
- Reservation `run_id` is unique but intentionally not FK-bound to `agent_runs.id` in model/migration to support pre-run reservation creation semantics safely.

## Key Files Added
- `backend/alembic/versions/3f8a1c2d9b7e_add_usage_quota_tables.py`
- `backend/app/db/postgres/models/usage_quota.py`
- `backend/app/services/usage_quota_service.py`
- `backend/app/agent/execution/stream_contract_v2.py`
- `backend/alembic/versions/7a1f3b4c5d6e_add_agent_threads_and_turns.py`
- `backend/app/db/postgres/models/agent_threads.py`
- `backend/app/services/thread_service.py`
- `backend/tests/usage_quota/test_usage_quota_service.py`
- `backend/tests/usage_quota/test_state.md`

## Key Files Updated (Core)
- `backend/app/agent/execution/service.py`
- `backend/app/agent/executors/standard.py`
- `backend/app/api/routers/agents.py`
- `backend/app/api/routers/published_apps_public.py`
- `backend/app/api/routers/published_apps_host_runtime.py`
- `backend/app/api/routers/admin.py`
- `backend/app/api/schemas/agents.py`
- `backend/main.py`
- `backend/app/middleware/published_apps_cors.py`
- `backend/app/workers/tasks.py`
- `backend/app/workers/celery_app.py`
- `backend/app/db/postgres/models/agents.py`
- `packages/runtime-sdk/src/core/types.ts`
- `packages/runtime-sdk/src/core/client.ts`
- `packages/runtime-sdk/src/core/events.ts`
- `packages/runtime-sdk/package.json`
- `frontend-reshet/src/hooks/useAgentRunController.ts`
- `frontend-reshet/src/hooks/useAgentExecution.ts`
- `frontend-reshet/src/services/chat.ts`
- `frontend-reshet/src/services/admin.ts`
- `frontend-reshet/src/services/types.ts`
- `frontend-reshet/src/components/admin/threads-table.tsx`
- `frontend-reshet/src/app/admin/threads/page.tsx`
- `frontend-reshet/src/app/admin/threads/[threadId]/page.tsx`
- `frontend-reshet/src/app/admin/users/[userId]/threads/[threadId]/page.tsx`

## Validation and Test Runs
- Backend suites:
  - `pytest -q backend/tests/usage_quota backend/tests/published_apps backend/tests/published_apps_host_runtime backend/tests/legacy_chat_bootstrap backend/tests/agent_tool_usecases/test_agent_execution_panel_stream_api.py`
  - Result: PASS (`32 passed`)
- Additional backend slices:
  - `pytest -q backend/tests/agent_api_context backend/tests/agent_resume_authorization`
  - Result: PASS (`5 passed`)
- Targeted post-worker-change backend slice:
  - `pytest -q backend/tests/usage_quota backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py::test_host_chat_stream_uses_cookie_auth_and_persists backend/tests/published_apps/test_admin_apps_crud.py::test_admin_users_list_block_unblock_and_revoke_session`
  - Result: PASS (`8 passed`)
- Frontend runtime SDK test:
  - `npm test -- --runInBand src/__tests__/runtime_sdk/runtime_sdk_core.test.ts`
  - Result: PASS (`4 passed`)
- Thread unification backend slices:
  - `pytest -q backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py backend/tests/published_apps/test_public_chat_scope_and_persistence.py backend/tests/published_apps/test_public_app_resolve_and_config.py::test_preview_runtime_bootstrap_contract`
  - Result: PASS (`9 passed`)
  - `pytest -q backend/tests/published_apps`
  - Result: PASS (`17 passed`)

## Known Follow-Ups
1. Full frontend cleanup for remaining `/chat` navigation references outside the redirected routes and disabled service methods.
2. Add explicit real-PostgreSQL concurrency race tests for row-lock behavior under `reserve_for_run`.
3. Continue reducing deprecation warnings (`datetime.utcnow`, Pydantic v2 config/dict usage) seen during test runs.
4. Align rollout toggles and production sequencing with operational monitoring dashboards before full enablement.

## Rollout Flags Used by This Implementation
- `STREAM_V2_ENFORCED`
- `QUOTA_ENFORCEMENT_ENABLED`
- `LEGACY_CHAT_DISABLED` (planned usage in rollout policy)
- `QUOTA_WORKERS_BEAT_ENABLED`
- `QUOTA_EXPIRE_SWEEP_INTERVAL_SECONDS`
- `QUOTA_RECONCILE_INTERVAL_SECONDS`
