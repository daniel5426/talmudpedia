# Coding Agent Run Stuck + Infinite Queue Debug Summary

Last Updated: 2026-02-22

## Reported Production Symptom
- In Apps Builder chat, coding-agent finishes visible work and outputs a final response, but run state never exits "running" (cube icon stays active indefinitely).
- Stop action is ineffective in this state.
- Any new user messages are queued forever because UI still believes a run is active.

## Repro Status
- User reports issue still reproduces after multiple backend fixes.
- Local targeted regressions pass, but live environment still shows stuck running indicator.

## Fixes Implemented So Far

### 1) OpenCode engine terminal short-circuit
- File: `backend/app/services/published_app_coding_agent_engines/opencode_engine.py`
- Change:
  - On mapped terminal events (`run.completed`, `run.failed`), engine now breaks out immediately instead of continuing stream consumption.
- Why:
  - Prevent engine from hanging when upstream keeps the stream open after terminal output.

### 2) Runtime stream terminal-aware finalization
- File: `backend/app/services/published_app_coding_agent_runtime.py`
- Change:
  - Runtime now stops waiting for more engine events once terminal event is observed.
  - Runtime closes engine iterator (`aclose`) defensively.
  - Runtime force-persists terminal run status (`completed`/`failed`) if terminal event arrived but DB status was still non-terminal.
- Why:
  - Prevent run lifecycle from remaining logically running due to provider stream behavior.

### 3) Official OpenCode global-event settle completion
- File: `backend/app/services/opencode_server_client.py`
- Change:
  - Added settle-based completion for official `/global/event` mode:
    - if assistant text exists,
    - no tools are running,
    - and settle window elapsed,
    - emit terminal `run.completed` even without explicit `session.idle`.
- Why:
  - Some providers do not emit final idle/terminal marker reliably.

### 4) New regression coverage added
- File: `backend/tests/coding_agent_api/test_terminal_stream_completion.py` (new)
- Coverage:
  - Engine emits terminal event then hangs forever -> runtime must still terminate run.
  - Both completion and failure paths validated.
- File: `backend/tests/opencode_server_client/test_opencode_server_client.py`
- Coverage:
  - Official global-event path settles to terminal completion without explicit `session.idle`.

### 5) Frontend stream resilience + terminal status reconciliation
- Files:
  - `frontend-reshet/src/features/apps-builder/workspace/chat/useAppsBuilderChat.ts`
  - `frontend-reshet/src/services/published-apps.ts`
- Change:
  - Reworked stream read loop to avoid indefinite hang on a pending `reader.read()` when terminal SSE never arrives.
  - Added persisted run-status reconciliation via `GET /admin/apps/{app_id}/coding-agent/runs/{run_id}` when stream exits without terminal event.
  - Stop/cancel now clears UI sending state immediately while still preserving queue safety (`pendingCancel` gate), removing the perceived post-click stop lag.
  - Added configurable stream guardrails (`STALL_TIMEOUT`, `MAX_DURATION`, read poll timeout) via frontend env overrides.
- Why:
  - Visible assistant output can arrive while terminal frame is lost/stalled on transport, leaving local `isSending` true and queue blocked.
  - UI now recovers from missing terminal SSE by trusting persisted backend terminal run state.

## Tests Executed and Outcomes
- `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_terminal_stream_completion.py`
  - PASS (2 passed)
- `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_opencode_apply_patch_recovery.py`
  - PASS (4 passed)
- `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py`
  - PASS (26 passed)
- `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_terminal_stream_completion.py tests/coding_agent_api/test_opencode_apply_patch_recovery.py tests/opencode_server_client/test_opencode_server_client.py`
  - PASS (32 passed)
- `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api`
  - FAIL (1 unrelated failure in model fixture setup: no active chat model in test data)
- `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps/apps_builder_workspace.test.tsx`
  - PASS (41 passed)

## Runtime/Env Signals Checked
- `backend/.env` contains:
  - `APPS_DRAFT_DEV_CONTROLLER_URL=http://127.0.0.1:8000/internal/sandbox-controller`
  - `APPS_CODING_AGENT_OPENCODE_BASE_URL=http://127.0.0.1:8788`

## Current Conclusion
- Root cause gap confirmed in frontend stream lifecycle: missing/undelivered terminal SSE could leave UI waiting indefinitely and block queued prompts.
- Frontend now has transport-safe read polling and backend status reconciliation fallback, plus regression coverage for the exact queue-stall sequence.
- Backend terminal handling fixes remain in place and complementary.

## Recommended Next Debug Iteration
- Deploy and verify in live environment with one full manual scenario:
  - Send prompt A, then queue prompt B before A completes.
  - Force/observe missing terminal SSE for A (if reproducible).
  - Confirm UI clears running state and automatically dequeues B after persisted terminal status reconciliation.
- Keep run-id scoped telemetry enabled temporarily to validate stream vs persisted status parity in production.
