# Artifact Coding Agent Tests

Last Updated: 2026-03-16

## Scope

Track backend coverage for the artifact-coding agent runtime across locked and standalone sessions, native conversation continuation, direct persistence, and function tool pack.

## Test Files Present

- test_runtime_service.py

## Key Scenarios Covered

- create-mode session scoping via `draft_key`
- lightweight seed-based draft initialization builds a canonical initial snapshot without falling back to a generic `agent_node`
- relinking from `draft_key` to `artifact_id` without creating a second shared draft
- scope-free architect-created sessions keep a stable direct `shared_draft_id` link and do not create a second shared draft on later resolution
- standalone sessions persist `scope_mode=standalone` and expose it in serialized runtime/session state
- standalone scope tools can search artifacts, open an existing artifact into the current session, and reset the session to a new draft
- locked sessions reject standalone-only scope switching tools
- `artifact-coding-persist-artifact` can create from an unbound standalone draft and relink the session to the canonical artifact
- artifact coding agent profile includes explicit delegated-worker instructions and the canonical `BLOCKING QUESTION:` blocker prefix
- helper-tool/session state export returns canonical `platform_assets_create_input` and `platform_assets_update_input`
- saved artifact session hydration rebuilds the working snapshot from the canonical artifact row
- stored `orchestrator` chat turns are mapped to model-facing `system` messages when rebuilding session history
- native `continue_prompt_run(...)` persists visible `orchestrator` turns and starts the next run from real stored session history on the same thread
- `prepare_session_run_input(...)` builds kernel-ready child-run payloads from true stored session history, uses the session's native `agent_thread_id`, and preserves `orchestrator` authority in model-facing messages
- runtime state serialization now exposes `persistence_readiness` separately from `verification_state`
- artifact test tools now enforce one active test run at a time and add a server-side `artifact_coding_await_last_test_result` wait path for Cloudflare cold-start / queue delay
- delegated artifact-worker instructions now tell the model to start one test run, wait for terminal result, and avoid `queued` polling loops

## Last Run

- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-14 20:39 EET
- Result: passed (`3 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-14 Asia/Hebron
- Result: Pass (5 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-14 21:13 Asia/Hebron
- Result: PASS (`4 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-15 00:04 EET
- Result: PASS (`5 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_sdk_tool/test_platform_sdk_actions.py`
- Date: 2026-03-15 00:27 EET
- Result: PASS (`55 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date: 2026-03-15 19:33 EET
- Result: PASS (`25 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_workers/test_architect_worker_integration.py`
- Date: 2026-03-15 20:18 EET
- Result: PASS (`30 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date: 2026-03-16 00:37 EET
- Result: PASS (`15 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date: 2026-03-16 00:37 EET
- Result: PASS (`33 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py`
- Date: 2026-03-16 01:16 Asia/Hebron
- Result: PASS (`38 passed`)

## Known Gaps

- router prompt-run execution is still not covered in this feature directory
- no backend integration test yet covers standalone playground session restoration through `chatSessionId`
- no test yet asserts live artifact test-run reconciliation after a child run
