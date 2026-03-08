# Platform Architect Runtime Tests

Last Updated: 2026-03-08

## Scope
- Platform Architect v1.2 direct domain-tool loop runtime (no `architect.run` path).
- Success, repair, approval-blocked, tenant/scope-denied, and replay idempotency behaviors.

## Test files present
- test_platform_architect_runtime.py
- test_architect_seeding.py

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

## Last run command + date/time + result
- Command: `cd backend && pytest -q tests/platform_architect_runtime/test_architect_seeding.py tests/platform_architect_runtime/test_platform_architect_runtime.py tests/platform_sdk_tool/test_platform_sdk_actions.py tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py`
- Date/Time: 2026-03-08
- Result: passed (`94 passed, 1 warning`)

## Known gaps or follow-ups
- Add integration coverage that exercises seeded `platform-architect` graph with real tool resolution in DB-backed test environment.
