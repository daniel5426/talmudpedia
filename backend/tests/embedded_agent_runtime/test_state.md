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
- Thread detail returns per-turn historical `run_events` for replaying old tool/reasoning/widget UI.
- Embedded runtime supports scoped thread deletion through the public embed surface.
- Attachment upload works through the public embed surface and attachment metadata is returned on thread turns.
- Document attachments are processed before execution and thread deletion removes stored attachment bytes.
- Cross-user thread reads fail.
- Cross-user thread deletes fail.
- Wrong-scope and revoked API keys are rejected.
- Draft agents cannot be embedded.

Last run command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia/backend python3 -m pytest -q /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py`
Last run date/time: 2026-03-19 14:42 Asia/Hebron
Last run result: pass (`5 passed`)

Known gaps / follow-ups:
- Add cross-agent thread read/delete coverage once multi-agent embed examples land.
- Add dedicated SDK/package integration tests for the new upload/delete/thread-history surfaces.
