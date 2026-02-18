# Coding Agent API Tests

Last Updated: 2026-02-18

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
- Run creation with explicit `model_id` persists `requested_model_id` and `resolved_model_id`.
- Run creation with unavailable `model_id` fails with `400` + `CODING_AGENT_MODEL_UNAVAILABLE`.
- Run creation with `engine=opencode` fails fast with deterministic `400` contracts when engine is unavailable (`CODING_AGENT_ENGINE_UNAVAILABLE`) or runtime path is unsupported (`CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME`).
- Auto model resolution pins `resolved_model_id` on run creation and remains stable even if tenant defaults change afterwards.
- Run creation tolerates non-fatal draft runtime prewarm failures and still persists run metadata.
- Execution service applies run-scoped model override onto graph node `model_id` fields.
- Stale `base_revision_id` conflict contract (`REVISION_CONFLICT`).
- Stream endpoint returns correctly framed SSE envelopes (`data: ...\n\n`) and executes coding-agent stream generator.
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

## Known gaps or follow-ups
- Add authorization-negative coverage for cross-tenant run access.
