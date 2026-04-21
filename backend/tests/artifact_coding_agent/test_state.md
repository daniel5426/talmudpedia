# Artifact Coding Agent Tests

Last Updated: 2026-04-22

## Scope

Track backend coverage for the artifact-coding agent runtime across locked draft sessions, native conversation continuation, and the function tool pack.

## Test Files Present

- test_runtime_service.py

## Key Scenarios Covered

- create-mode session scoping via `draft_key`
- lightweight seed-based draft initialization builds a canonical initial snapshot without falling back to a generic `agent_node`
- relinking from `draft_key` to `artifact_id` without creating a second shared draft
- scope-free architect-created sessions keep a stable direct `shared_draft_id` link and do not create a second shared draft on later resolution
- artifact coding agent profile includes delegated-worker instructions while keeping artifact-scope refusals brief and surface-agnostic
- helper-tool/session state export returns canonical `platform_assets_create_input` and `platform_assets_update_input`
- helper-tool/session state export returns canonical artifact payloads without a draft/authored slug field
- saved artifact session hydration rebuilds the working snapshot from the canonical artifact row
- stored `orchestrator` chat turns are mapped to model-facing `system` messages when rebuilding session history
- native `continue_prompt_run(...)` persists visible `orchestrator` turns and starts the next run from real stored session history on the same thread
- `prepare_session_run_input(...)` builds kernel-ready child-run payloads from true stored session history, uses the session's native `agent_thread_id`, and preserves `orchestrator` authority in model-facing messages
- `prepare_session_run_input(...)` no longer injects the live prompt into `messages`, so the generic executor remains the single source of current-turn insertion and artifact-coding runs avoid duplicate latest-user turns
- architect-worker continuation now stays separate from true orchestrator/system instructions, so only explicit orchestrator control turns map to model-facing `system`
- runtime state serialization now exposes `persistence_readiness` separately from `verification_state`
- artifact coding tools now resolve against the run-pinned shared draft even if the mutable session binding changes later
- project-scoped artifact-coding sessions/shared drafts now preserve `project_id` through prepare, relink, lookup, and run-pinned draft resolution
- completed artifact-coding runs that emitted `tool.failed` are reconciled to true failed runs and persist a failure assistant message instead of a false success summary
- session-detail reload now returns run events for runs that only have a stored user turn, so failed/interrupted partial history is still reconstructible from trace events
- artifact prompt submission now creates the backing `agent_thread_turn` immediately, so admin thread detail does not go blank when a run is aborted before executor startup finishes
- artifact cancel now persists the cancelled thread turn plus any streamed partial assistant text, keeping admin thread detail and artifact chat history aligned after a manual abort
- artifact test tools now enforce one active test run at a time and add a server-side `artifact_coding_await_last_test_result` wait path for Cloudflare cold-start / queue delay
- artifact test tools now return ordered run events and a failure summary so the agent can inspect why a test failed
- delegated artifact-worker instructions now tell the model to start one test run, wait for terminal result, and avoid `queued` polling loops
- delegated artifact-worker instructions now include an explicit draft-readiness checklist for new artifacts, covering display_name, kind, source files, entry module, runtime target, capabilities, config schema, dependencies, and the matching contract payload
- delegated artifact-worker instructions now cover both `python` and `javascript`, create-only language selection, safe credential-reference authoring, and `tool_impl` lifecycle boundaries
- contract mutation now uses kind-specific tools with exact contract schemas, so the model no longer needs a generic `contract_payload` wrapper path
- tool-contract mutation now normalizes stringified nested `input_schema`, `output_schema`, and `tool_ui` objects before persisting the draft
- source editing now uses exact `old_text` replacement plus numbered read/search context instead of fragile line-range patch guessing
- read-file now accepts one-sided line bounds and large-file default reads through bounded windows instead of rejecting partial ranges or dumping full huge files
- the coding-agent tool surface now includes explicit runtime-contract validation for the required `execute(inputs, config, context)` entrypoint
- artifact coding runtime can build javascript create-mode starter drafts from seed input
- artifact coding tool surface now includes safe credential metadata listing for `@{credential-id}` authoring without exposing secret values
- scope-conflict prompt behavior now refuses briefly without asking for new sessions, new artifacts, or scaffold follow-up
- tool execution scope is now derived strictly from the run-bound session/shared-draft context, not caller-supplied payload overrides
- existing artifact-coding chats now reject mismatched `artifact_id` / `draft_key` rebinding attempts instead of silently rewriting scope
- run lookup/control paths now enforce bound-session ownership for the current user even when the requested run is not the session's latest run
- artifact run serializers now expose canonical `context_window` snapshots plus `run_usage` for chat-session/runtime consumers
- artifact write tools now return compact mutation results without embedding full `draft_snapshot` payloads
- artifact draft refresh now has a dedicated session snapshot read path instead of relying on tool result snapshots

## Last Run

- Command: `PYTHONPATH=. pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`35 passed, 5 warnings`)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`31 passed, 5 warnings`)
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
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-16 16:13 EET
- Result: PASS (`16 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-16 17:14 EET
- Result: PASS (`11 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_artifact_versions_api.py backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/control_plane_sdk/test_client_and_modules.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py`
- Date: 2026-03-16 19:41 EET
- Result: PASS (`145 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date: 2026-03-16 20:12 EET
- Result: PASS (`15 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-25 12:46 EET
- Result: PASS (`13 passed, 2 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-25 Asia/Hebron
- Result: PASS (`14 passed, 2 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-25 Asia/Hebron
- Result: PASS (`34 passed, 7 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-25 17:07 EET
- Result: PASS (`19 passed, 7 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_tool_loop/test_tool_loop.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-25 17:53 EET
- Result: PASS (`25 passed, 6 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-27 Asia/Hebron
- Result: PASS (`23 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-27 Asia/Hebron
- Result: PASS (`25 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`27 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`30 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-29 21:59 EEST
- Result: PASS (`32 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-29 22:00 EEST
- Result: PASS (`35 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-30 01:07 EEST
- Result: PASS (`36 passed, 5 warnings`)
- Command: `TEST_USE_REAL_DB=0 SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py::test_runtime_service_relinks_draft_key_to_saved_artifact_without_new_shared_draft backend/tests/artifact_coding_agent/test_runtime_service.py::test_prepare_session_without_scope_keeps_direct_shared_draft_link backend/tests/artifact_coding_agent/test_runtime_service.py::test_artifact_tools_use_run_pinned_shared_draft_when_session_binding_changes`
- Date: 2026-04-22 Asia/Hebron
- Result: PASS (`3 passed`)

## Known Gaps

- router prompt-run execution is still not covered in this feature directory
- no test yet asserts live artifact test-run reconciliation after a child run
