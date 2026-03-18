# Test State: Backend Test Env Bootstrap

Last Updated: 2026-03-18

## Scope
- Shared backend env-file resolution for tests and runtime startup.
- Repo-safe test profile defaults and guardrails around test env loading behavior.

## Test files present
- test_env_loader.py

## Key scenarios covered
- Explicit env-file override takes precedence.
- Missing explicit env-file override fails loudly.
- Test profile prefers `.env.test` / `.env.test.example` over `.env`.
- Non-test profile falls back to `.env`.
- Test env loading preserves existing shell values when override is disabled.
- Missing default env files return `None` when loading is optional.
- Pytest runtime detection is explicit.

## Last run command + date/time + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/test_env_bootstrap/test_env_loader.py`
- Date/Time: 2026-03-18 16:34 EET
- Result: passed (`7 passed, 1 warning`)
- Command: `backend/scripts/dev-services/run_backend_tests.sh backend/tests/test_env_bootstrap/test_env_loader.py -q`
- Date/Time: 2026-03-18 16:34 EET
- Result: passed (`7 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/test_env_bootstrap backend/tests/node_inventory backend/tests/builtin_tools_registry/test_builtin_registry_api.py`
- Date/Time: 2026-03-18 16:42 EET
- Result: passed (`23 passed, 6 warnings`)

## Known gaps or follow-ups
- Add command-level coverage for the new test-stack helper scripts once the broader stack bootstrap/reset slice lands.
