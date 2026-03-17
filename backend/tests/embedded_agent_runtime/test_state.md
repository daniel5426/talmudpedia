# Embedded Agent Runtime Tests

Last Updated: 2026-03-17

Scope:
- Public embedded-agent runtime routes authenticated by tenant API keys.
- Embedded thread ownership by tenant, published agent, and `external_user_id`.

Test files present:
- test_embedded_agent_runtime_api.py

Key scenarios covered:
- Published agents stream successfully through `/public/embed/agents/{agent_id}/chat/stream`.
- Stream responses emit `run-stream.v2` envelopes and `X-Thread-ID`.
- Embedded runtime persists thread ownership and exposes scoped thread history.
- Cross-user thread reads fail.
- Wrong-scope and revoked API keys are rejected.
- Draft agents cannot be embedded.

Last run command: `cd backend && PYTHONPATH=. pytest -q tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py`
Last run date/time: 2026-03-17 18:30 EET
Last run result: pass (`3 tests`)

Known gaps / follow-ups:
- Add cross-agent thread-access coverage once multi-agent embed examples land.
- Add explicit terminal-event assertions if the embed stream contract changes beyond `run-stream.v2`.
