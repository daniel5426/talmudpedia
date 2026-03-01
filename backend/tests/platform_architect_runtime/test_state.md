# Platform Architect Runtime Tests

Last Updated: 2026-03-02

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

## Last run command + date/time + result
- Command: `cd backend && pytest -q tests/platform_architect_runtime/test_platform_architect_runtime.py tests/platform_architect_runtime/test_architect_seeding.py tests/platform_sdk_tool/test_platform_sdk_actions.py tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py`
- Date/Time: 2026-03-02 01:07:59 EET
- Result: pass (`62 passed, 1 warning`)

## Known gaps or follow-ups
- Add integration coverage that exercises seeded `platform-architect` graph with real tool resolution in DB-backed test environment.
