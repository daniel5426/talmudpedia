# Embedded Agent Runtime Tests

Last Updated: 2026-03-16

Scope:
- Public embedded-agent runtime routes authenticated by tenant API keys.
- Embedded thread ownership by tenant, published agent, and `external_user_id`.

Test files present:
- test_embedded_agent_runtime_api.py

Key scenarios covered:
- Published agents stream successfully through `/public/embed/agents/{agent_id}/chat/stream`.
- Embedded runtime persists thread ownership and exposes scoped thread history.
- Cross-user thread reads fail.
- Wrong-scope and revoked API keys are rejected.
- Draft agents cannot be embedded.

Last run command: `cd backend && PYTHONPATH=. pytest -q tests/tenant_api_keys/test_api_keys_api.py tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py tests/control_plane_sdk tests/published_apps_external_runtime/test_external_runtime_api.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py tests/security_scope_registry/test_scope_registry.py`
Last run date/time: 2026-03-16 19:38 EET
Last run result: pass (`45 passed, 2 skipped`)

Known gaps / follow-ups:
- Add cross-agent thread-access coverage once multi-agent embed examples land.
- Add explicit SSE terminal-event assertions if the embed stream contract changes beyond `run-stream.v2`.
