# Platform Architect Runtime Tests

Last Updated: 2026-03-12

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
- Non-canonical Platform SDK contract failures are treated as immediate blocker conditions for architect mutation branches.
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
- Seeded architect runtime no longer forces JSON-only output in prompt or node config.
- Seeded architect runtime now defaults `temperature` to `1`.
- Architect domain tools bind to local `platform_sdk` function dispatch instead of artifact-worker execution.
- Local `platform_sdk` function dispatch forwards the correct architect domain tool slug.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -q tests/platform_architect_runtime/test_architect_seeding.py`
- Date/Time: 2026-03-10 19:02 EET
- Result: passed (`3 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_runtime backend/tests/tool_execution/test_function_tool_execution.py::test_function_tool_execution backend/tests/tool_execution/test_function_tool_execution.py::test_function_tool_propagates_delegation_context`
- Date/Time: 2026-03-12 02:04 EET
- Result: passed (`20 passed, 5 warnings`)

## Known gaps or follow-ups
- Add integration coverage that exercises seeded `platform-architect` graph with real tool resolution in DB-backed test environment.
