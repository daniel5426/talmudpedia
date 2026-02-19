# Coding Agent Sandbox Isolation Tests

Last Updated: 2026-02-19

## Scope of the feature
- Run-level sandbox isolation guardrails for coding-agent execution paths.
- Fail-closed behavior when sandbox-controller mode is required but unavailable.

## Test files present
- `backend/tests/coding_agent_sandbox_isolation/test_run_sandbox_isolation.py`

## Key scenarios covered
- `engine=opencode` run creation is rejected with deterministic `400` contract when sandbox-required mode is enabled but no controller URL is configured.
- Run stream fails closed when a queued run lacks run-scoped sandbox context and sandbox recovery is unavailable.
- Run sandbox session persistence uses controller-provided `workspace_path` (instead of generic `/workspace` fallback) when session start returns it.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_sandbox_isolation/test_run_sandbox_isolation.py -q`
- Date: 2026-02-19 03:06:08 EET
- Result: PASS (3 passed)
- Command: `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py tests/sandbox_controller/test_dev_shim.py tests/coding_agent_sandbox_isolation/test_run_sandbox_isolation.py -q`
- Date: 2026-02-19 03:21:28 EET
- Result: PASS (29 passed overall, including sandbox-isolation coverage)

## Known gaps or follow-ups
- Add coverage for cross-tenant sandbox visibility constraints once multi-tenant queue admission lands.
