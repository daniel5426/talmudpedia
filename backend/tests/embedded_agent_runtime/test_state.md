# Embedded Agent Runtime Tests

Last Updated: 2026-04-12

Scope:
- Public embedded-agent runtime routes authenticated by tenant API keys.
- Embedded thread ownership by tenant, published agent, and `external_user_id`.

Test files present:
- test_embedded_agent_runtime_api.py

Key scenarios covered:
- Published agents stream successfully through `/public/embed/agents/{agent_id}/chat/stream`.
- Stream responses emit detached `run-stream.v2` envelopes from persisted run events and `X-Thread-ID`.
- Embedded runtime persists thread ownership and exposes scoped thread history.
- Thread detail returns canonical `response_blocks` plus historical `run_events` for debug/inspection.
- Thread detail preserves separate `assistant_output_text` and `final_output` values on persisted turns.
- Thread detail can return nested `lineage` and `subthread_tree` payloads when `include_subthreads=true`.
- Embedded runtime supports scoped thread deletion through the public embed surface.
- Attachment upload works through the public embed surface and attachment metadata is returned on thread turns.
- Document attachments are processed before execution and thread deletion removes stored attachment bytes.
- Cross-user thread reads fail.
- Cross-user thread deletes fail.
- Wrong-scope and revoked API keys are rejected.
- Draft agents cannot be embedded.

Last run command: `TEST_USE_REAL_DB=0 PYTHONPATH=backend python3 -m pytest -q backend/tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py backend/tests/published_apps/test_public_chat_scope_and_persistence.py backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
Last run date/time: 2026-04-09 Asia/Hebron
Last run result: pass (`26 passed`)

Known gaps / follow-ups:
- Add cross-agent thread read/delete coverage once multi-agent embed examples land.
- Add dedicated SDK/package integration tests for the new upload/delete/thread-history surfaces.
