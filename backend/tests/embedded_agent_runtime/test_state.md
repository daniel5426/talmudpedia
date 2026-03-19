# Embedded Agent Runtime Tests

Last Updated: 2026-03-19

Scope:
- Public embedded-agent runtime routes authenticated by tenant API keys.
- Embedded thread ownership by tenant, published agent, and `external_user_id`.

Test files present:
- test_embedded_agent_runtime_api.py

Key scenarios covered:
- Published agents stream successfully through `/public/embed/agents/{agent_id}/chat/stream`.
- Stream responses emit `run-stream.v2` envelopes and `X-Thread-ID`.
- Embedded runtime persists thread ownership and exposes scoped thread history.
- Thread detail returns per-turn historical `run_events` for replaying old tool/reasoning UI.
- Embedded runtime supports scoped thread deletion through the public embed surface.
- Attachment upload works through the public embed surface and attachment metadata is returned on thread turns.
- Document attachments are processed before execution and thread deletion removes stored attachment bytes.
- Cross-user thread reads fail.
- Cross-user thread deletes fail.
- Wrong-scope and revoked API keys are rejected.
- Draft agents cannot be embedded.

Last run command: `pytest -q backend/tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py backend/tests/agent_threads/test_thread_service.py`
Last run date/time: 2026-03-19 16:28 Asia/Hebron
Last run result: pass (`7 tests` + `2` thread-service tests)

Known gaps / follow-ups:
- Add cross-agent thread read/delete coverage once multi-agent embed examples land.
- Add dedicated SDK/package integration tests for the new upload/delete/thread-history surfaces.
