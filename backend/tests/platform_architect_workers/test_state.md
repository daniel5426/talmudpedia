# Platform Architect Workers Tests State

Last Updated: 2026-03-16

## Scope of the feature
Focused coverage for the architect-specific async worker runtime, binding-backed artifact delegation flow, and seeded architect DB-backed orchestration behavior.

## Test files present
- `test_worker_runtime.py`
- `test_architect_worker_integration.py`

## Key scenarios covered
- Worker tool seeding and prompt/tool-surface assertions for the seeded architect.
- Lightweight `architect-worker-binding-prepare` create flow uses `title_prompt + draft_seed.kind`, while advanced full snapshot seeding is isolated to `seed_snapshot`.
- Async worker runtime behavior including duplicate-binding rejection in group spawn.
- Child-run inspection returning binding metadata from run records.
- Child-run waiting-state detection from delegated-worker blocker output and server-side `architect-worker-await` behavior.
- Architect continuation of a waiting or already-completed child through `architect-worker-respond`, including native continuation of binding-backed artifact workers through the existing worker session/thread history.
- Kernel-owned continuation of a completed artifact worker through `architect-worker-respond`, including preserved architect lineage, `parent_node_id=architect_worker_respond`, and reuse of the native artifact session thread id from the initial spawn.
- `architect-worker-respond` now emits execution-trace events that expose whether response handling resumed a paused run or started native conversation continuation and which thread ids were involved.
- Binding-owned artifact persistence through `architect-worker-binding-persist-artifact`, including auto-create and explicit mode rejection.
- Binding persistence readiness gating prevents create-mode artifact persistence when required metadata like `slug` or `display_name` is still missing.
- Binding/session state now exposes a separate `verification_state` for latest artifact test-run status, instead of overloading `persistence_readiness`.
- DB-backed seeded architect run that prepares an artifact binding, spawns an artifact worker, waits, and persists the canonical artifact successfully without a `platform-assets` artifact-create call in the architect path.
- DB-backed seeded architect run that attempts a second mutating spawn on the same binding and reports the active-binding blocker cleanly.
- Strict architect worker tool schemas reject malformed model payloads before runtime dispatch, including the observed bad binding-create guesses (`create`, `files`, `entrypoint`, `text`), while still allowing executor-owned runtime metadata to flow separately.
- Architect worker spawn/binding schema failures now expose explicit branch/type diagnostics, including missing `worker_agent_slug` or `binding_ref` and wrong `objective` types.
- Architect replies sent through `architect-worker-respond` now continue worker conversations as model-facing `user` turns instead of `system` turns, so worker question/answer follow-ups match native chat semantics.
- Binding-exported artifact payloads remain available for inspection/debugging, but the normal worker-backed persistence path is now runtime-owned instead of model pass-through.
- Spawned architect worker context now carries the canonical `artifact_coding_shared_draft_id` derived from the prepared binding session.
- Completed artifact-worker continuation no longer uses synthetic `messages=[]` follow-up spawn payloads; continuation is history-native, kernel-owned, and persisted with visible `orchestrator` role chat turns.
- Binding-backed spawn now uses the native worker session thread id from the first architect child run, so spawn and continuation share one worker conversation thread.
- Artifact worker validation now has a server-side `artifact-coding-await-last-test-result` path, and duplicate in-flight test starts fail explicitly instead of queue-spamming.
- Artifact-coding delegated workers now mutate and validate the shared draft only; architect-owned binding persistence remains the canonical completion path.

## Last run command + date/time + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py`
- Date/Time: 2026-03-14 20:39 EET
- Result: PASS (`89 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-14 21:13 Asia/Hebron
- Result: PASS (`18 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date/Time: 2026-03-15 00:04 EET
- Result: PASS (`22 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_sdk_tool/test_platform_sdk_actions.py`
- Date/Time: 2026-03-15 00:27 EET
- Result: PASS (`55 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-15 01:01 Asia/Hebron
- Result: PASS (`19 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py`
- Date/Time: 2026-03-15 01:47 Asia/Hebron
- Result: PASS (`13 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-15 18:32 Asia/Hebron
- Result: PASS (`18 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-15 19:33 EET
- Result: PASS (`25 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_workers/test_architect_worker_integration.py`
- Date/Time: 2026-03-15 20:18 EET
- Result: PASS (`30 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-16 00:37 EET
- Result: PASS (`33 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py`
- Date/Time: 2026-03-16 01:16 Asia/Hebron
- Result: PASS (`38 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py`
- Date/Time: 2026-03-16 15:35 EET
- Result: PASS (`18 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py`
- Date/Time: 2026-03-16 16:13 EET
- Result: PASS (`18 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py`
- Date/Time: 2026-03-16 17:14 EET
- Result: PASS (`18 passed, 1 warning`)

## Known gaps or follow-ups
- Group fanout is covered at runtime level, but there is not yet a DB-backed seeded architect E2E for parallel multi-binding spawn/join.
- Live real-DB smoke coverage exists separately in `backend/tests/platform_architect_e2e/` and remains opt-in/manual.
