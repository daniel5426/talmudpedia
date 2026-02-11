# Legacy Chat Bootstrap Tests

Last Updated: 2026-02-11

## Scope
Verifies legacy `/chat` router bootstrap behavior is lazy and does not instantiate external dependencies during module import.

## Test files present
- test_lazy_agent_initialization.py

## Key scenarios covered
- Importing `app.api.routers.agent` does not call `AgentFactory.create_agent`.
- `get_chat_agent()` initializes exactly once and reuses the cached instance.

## Last run command + result
- Command: `pytest -q backend/tests/legacy_chat_bootstrap backend/tests/agent_resume_authorization backend/tests/tools_guardrails -vv`
- Date/Time: 2026-02-11 22:17:10 EET
- Result: pass (11 passed)

## Known gaps or follow-ups
- Add API-level regression test ensuring `/chat` returns a controlled error when lazy bootstrap fails.
