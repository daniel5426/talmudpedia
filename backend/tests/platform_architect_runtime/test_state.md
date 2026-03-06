# Platform Architect Runtime Tests

Last Updated: 2026-03-06

## Scope
- Platform Architect v1.1 direct domain-tool loop runtime (no `architect.run` path).
- Success, repair, approval-blocked, tenant/scope-denied, and replay idempotency behaviors.

## Test files present
- test_platform_architect_runtime.py
- test_architect_seeding.py

## Key scenarios covered
- Happy path executes direct `rag.*` and `agents.*` calls for create/compile/validate/execute.
- Recovery path handles first compile failure, applies patch action, and succeeds on retry.
- Approval-sensitive mutation maps to `blocked_approval` with explicit next actions.
- Domain tool boundaries deny cross-domain action usage with `SCOPE_DENIED`.
- Missing tenant context for mutations fails with deterministic `TENANT_REQUIRED`.
- Replay path reuses existing resources rather than duplicating them.
- `agents.create` propagates structured SDK validation details (including normalized `validation_errors`) for deterministic repair.
- Platform architect domain schema includes `agents.nodes.catalog/schema/validate` action contracts.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py`
- Date/Time: 2026-03-06 (local run during this change set)
- Result: pass (`10 passed, 1 warning`)

## Known gaps or follow-ups
- Add integration coverage that exercises seeded `platform-architect` graph with real tool resolution in DB-backed test environment.
