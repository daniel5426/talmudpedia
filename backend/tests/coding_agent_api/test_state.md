# Coding Agent API Tests

Last Updated: 2026-02-19

## Scope of the feature
- Admin coding-agent run lifecycle APIs under `/admin/apps/{app_id}/coding-agent/runs*`.
- Request/response contract coverage for create/list/get/stream/resume/cancel.

## Test files present
- `backend/tests/coding_agent_api/test_run_lifecycle.py`

## Key scenarios covered
- Run creation through new coding-agent endpoint with app/revision linkage.
- Run creation forwards normalized prior chat turns (`messages`) and appends the current user prompt for stateful follow-up behavior.
- Run creation defaults `execution_engine` to `native` when omitted.
- Run creation supports explicit `engine=opencode` and persists run-level execution-engine audit data.
- Run creation provisions run-scoped sandbox context and returns sandbox metadata fields (`sandbox_id`, `sandbox_status`, `sandbox_started_at`).
- Run creation with explicit `model_id` persists `requested_model_id` and `resolved_model_id`.
- Run creation with unavailable `model_id` fails with `400` + `CODING_AGENT_MODEL_UNAVAILABLE`.
- Run creation with `engine=opencode` fails fast with deterministic `400` contracts when engine is unavailable (`CODING_AGENT_ENGINE_UNAVAILABLE`) or runtime path is unsupported (`CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME`).
- Run creation with `engine=opencode` fails with deterministic `400` contract when sandbox-required mode is enabled but sandbox controller mode is unavailable (`CODING_AGENT_SANDBOX_REQUIRED`).
- Run creation with `engine=opencode` resolves `opencode_model_id` from tenant/global provider bindings (backend-authoritative mapping) and passes it in run context.
- Run creation snapshots files from the active builder draft sandbox (when available) and seeds coding run base revision from that live snapshot.
- Run creation snapshot sanitization drops generated artifacts (`dist`, `.vite`, `*.tsbuildinfo`) before persisting the refreshed draft revision.
- Auto model resolution pins `resolved_model_id` on run creation and remains stable even if tenant defaults change afterwards.
- Execution service applies run-scoped model override onto graph node `model_id` fields.
- Stale `base_revision_id` conflict contract (`REVISION_CONFLICT`).
- Stream endpoint returns correctly framed SSE envelopes (`data: ...\n\n`) and executes coding-agent stream generator.
- Stream endpoint fails closed when a run is missing sandbox context and returns `run.failed` with sandbox-required diagnostics.
- Stream endpoint attempts sandbox-context recovery/bootstrap before failing closed on missing sandbox metadata.
- Completed runs auto-apply/checkpoint from run sandbox before sandbox teardown, avoiding end-of-run snapshot races.
- OpenCode engine accepts `coding_run_sandbox_*` context as fallback to avoid missing `sandbox_id` start failures.
- OpenCode run finalization now fails when `apply_patch` fails and no later successful `apply_patch` result is observed, preventing false-positive "completed" runs.
- OpenCode run finalization still allows recovered flows where an initial `apply_patch` failure is followed by a successful patch apply.
- Runtime stream emits `assistant.delta` from final persisted output when token streaming is empty.
- Runtime stream emits prompt-aware assistant fallback text when final output is missing.
- Runtime stream handles detached/non-persistent `AgentRun` instances by reloading the run row from DB before finalize/refresh paths.
- Runtime event mapping enriches patch tool failures with structured diagnostics (failure count + recommended refresh window).
- Resume endpoint accepts paused runs and rejects non-paused runs.
- Cancel endpoint transitions active runs to `cancelled`.
- OpenCode cancellation follows fail-closed semantics: unconfirmed upstream cancellation transitions run to `failed`.
- OpenCode stream path follows fail-closed semantics: adapter/runtime exceptions transition run to `failed` and emit `run.failed`.

## Last run command + date/time + result
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api backend/tests/coding_agent_checkpoints`
- Date: 2026-02-16 23:11 UTC
- Result: PASS (9 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Date: 2026-02-16 23:31 UTC
- Result: PASS (7 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Date: 2026-02-16 23:49 UTC
- Result: PASS (7 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py backend/tests/tool_execution/test_function_tool_execution.py`
- Date: 2026-02-17 22:52 UTC
- Result: PASS (17 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py backend/tests/tool_execution/test_function_tool_execution.py`
- Date: 2026-02-17 23:36 UTC
- Result: PASS (17 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Date: 2026-02-17 20:04 UTC
- Result: PASS (12 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Date: 2026-02-17 20:41 UTC
- Result: PASS (12 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/tool_execution backend/tests/coding_agent_api/test_run_lifecycle.py`
- Date: 2026-02-17 23:31 UTC
- Result: PASS (38 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_runtime_editing/test_patch_runtime.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py backend/tests/coding_agent_api/test_run_lifecycle.py`
- Date: 2026-02-18 00:25 UTC
- Result: PASS (26 passed)
- Command: `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Date: 2026-02-18 12:58 UTC
- Result: PASS (18 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-18 15:26:23 EET
- Result: PASS (19 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-18 16:07:09 EET
- Result: PASS (19 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-18 16:15:47 EET
- Result: PASS (19 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-18 23:34:43 UTC
- Result: PASS (19 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py tests/coding_agent_sandbox_isolation tests/sandbox_controller tests/opencode_server_client/test_opencode_server_client.py -q`
- Date: 2026-02-19 01:42:11 EET
- Result: PASS (42 passed overall, including coding-agent API coverage)
- Command: `cd backend && PYTHONPATH=. pytest tests/sandbox_controller tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 01:47:04 EET
- Result: PASS (22 passed overall, including coding-agent API coverage)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_sandbox_isolation tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 01:53:29 EET
- Result: PASS (21 passed overall, including coding-agent API coverage)
- Command: `cd backend && PYTHONPATH=. pytest tests/sandbox_controller/test_opencode_controller_proxy.py tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 01:57:37 EET
- Result: PASS (23 passed overall, including coding-agent API coverage)
- Command: `cd backend && PYTHONPATH=. pytest tests/sandbox_controller tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 02:23:11 EET
- Result: PASS (25 passed overall, including coding-agent API coverage)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 02:45:16 EET
- Result: PASS (21 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 02:47:47 EET
- Result: PASS (21 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/sandbox_controller/test_dev_shim.py tests/coding_agent_sandbox_isolation/test_run_sandbox_isolation.py tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 03:06:08 EET
- Result: PASS (27 passed overall, including coding-agent API coverage)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 03:13:09 EET
- Result: PASS (22 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 03:32:18 EET
- Result: PASS (24 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py tests/sandbox_controller/test_dev_shim.py tests/coding_agent_sandbox_isolation/test_run_sandbox_isolation.py -q`
- Date: 2026-02-19 03:21:28 EET
- Result: PASS (29 passed overall, including coding-agent API coverage)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q`
- Date: 2026-02-19 04:22 UTC
- Result: PASS (24 passed)

## Known gaps or follow-ups
- Add authorization-negative coverage for cross-tenant run access.
