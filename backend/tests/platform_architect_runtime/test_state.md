# Platform Architect Runtime Tests

Last Updated: 2026-03-15

## Scope
- Platform Architect v1.2 direct domain-tool loop runtime (no `architect.run` path).
- Success, repair, approval-blocked, tenant/scope-denied, and replay idempotency behaviors.

## Test files present
- test_platform_architect_runtime.py
- test_architect_seeding.py
- test_local_platform_sdk_tools.py

## Key scenarios covered
- Happy path executes direct `rag.*` and `agents.*` calls for create/compile/validate/execute.
- Recovery path handles first compile failure, applies patch action, and succeeds on retry.
- Repeated identical architect mutation failures now stop with a blocker instead of looping indefinitely.
- Non-canonical Platform SDK contract failures now get three repair retries before blocking, and blocker attribution preserves the wrapped attempted action instead of collapsing to `noop`.
- Unsupported RAG actions get one replan opportunity and then block instead of looping.
- Repeated identical architect mutation failures now block on the fifth matching failure instead of the second.
- RAG create blocker payloads preserve FastAPI-style field validation details and derive a readable target from create payload names.
- Approval-sensitive mutation maps to `blocked_approval` with explicit next actions.
- Domain tool boundaries deny cross-domain action usage with `SCOPE_DENIED`.
- Missing tenant context for mutations fails with deterministic `TENANT_REQUIRED`.
- Runtime tenant context is sufficient for mutations even when payload omits `tenant_id`.
- Explicit payload tenant override is rejected when it conflicts with runtime tenant context.
- Replay path reuses existing resources rather than duplicating them.
- `agents.create` propagates structured SDK validation details (including normalized `validation_errors`) for deterministic repair.
- Platform architect domain schema includes `agents.nodes.catalog/schema/validate` action contracts.
- Platform architect domain schema now includes `rag.operators.catalog/schema` action contracts for RAG-native discovery.
- Platform architect domain schema now includes `agents.create_shell` and `rag.create_pipeline_shell` as the preferred lightweight creation actions.
- Seeded architect runtime no longer forces JSON-only output in prompt or node config.
- Seeded architect runtime now defaults `temperature` to `1`.
- Seeded architect prompt now instructs artifact binding creation through `title_prompt + draft_seed.kind` and explicitly forbids low-level guesses like `create`, `files`, `entrypoint`, and `text`.
- Seeded architect prompt now requires worker-backed artifact persistence through `architect-worker-binding-persist-artifact`, with `architect-worker-binding-get-state` reduced to inspection/debugging.
- Architect domain tools bind to local `platform_sdk` function dispatch instead of artifact-worker execution.
- Local `platform_sdk` function dispatch forwards the correct architect domain tool slug.
- Local `platform_sdk` function dispatch emits internal trace events for the prepared runtime context and the completed SDK result.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -q tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-10 19:02 EET
- Result: passed (`3 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime backend/tests/tool_execution/test_function_tool_execution.py::test_function_tool_execution backend/tests/tool_execution/test_function_tool_execution.py::test_function_tool_propagates_delegation_context`
- Date/Time: 2026-03-12 02:04 EET
- Result: passed (`20 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_sdk_tool/test_platform_sdk_actions.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_architect_runtime/test_local_platform_sdk_tools.py backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py`
- Date/Time: 2026-03-12 03:07 EET
- Result: passed (`28 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime/test_local_platform_sdk_tools.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_sdk_tool/test_platform_sdk_actions.py backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py`
- Date/Time: 2026-03-12 03:39 EET
- Result: passed (`28 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-14 20:39 EET
- Result: passed (`10 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-15 01:01 Asia/Hebron
- Result: passed (`19 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/tool_execution/test_reasoning_tool_call_chunk_buffering.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_sdk_tool/test_platform_sdk_actions.py`
- Date/Time: 2026-03-15 00:27 EET
- Result: passed (`55 passed`)

## Known gaps or follow-ups
- Add integration coverage that exercises seeded `platform-architect` graph with real tool resolution in DB-backed test environment.
