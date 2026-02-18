Last Updated: 2026-02-19

## Scope
- OpenCode server client transport compatibility for coding-agent engine runs.
- Official API mode (`/global/health`, `/global/event`, `/session*`).
- Legacy API fallback mode (`/health`, `/v1/runs*`).

## Test Files
- `backend/tests/opencode_server_client/test_opencode_server_client.py`
- `backend/tests/opencode_server_client/test_opencode_server_client_live.py`

## Key Scenarios Covered
- Official mode unwraps `{success,data}` and supports `prompt_async` with fallback to `POST /session/{id}/message`.
- Global event stream translation emits incremental `assistant.delta` tokens and tool lifecycle events (`tool.started` / `tool.completed` / `tool.failed`).
- Global event parsing preserves early tool events even before assistant message-role metadata lands.
- Reasoning parts are filtered out from user-visible assistant deltas.
- Incremental text offset tracking prevents duplicate text when `/global/event` and `/session/{id}/message` overlap.
- Recoverable tool-step errors in earlier assistant turns no longer force terminal run failure when a later assistant turn succeeds.
- Snapshot polling fallback remains compatible (empty response recovery, wrapped payloads, missing `parentID`, read-timeout recovery).
- Session creation includes workspace external-directory permission rules.
- Missing assistant text still fails closed with deterministic diagnostics.
- Live roundtrip and live full-task edit flows are validated against a real OpenCode daemon.

## Last Run
- Command: `cd backend && PYTHONPATH=. pytest tests/opencode_server_client -q`
- Date/Time: 2026-02-19 00:19:21 EET
- Result: Pass (19 passed, 2 skipped, 1 warning)
- Command: `cd backend && OPENCODE_LIVE_TEST=1 OPENCODE_LIVE_FULL_TASK=1 APPS_CODING_AGENT_OPENCODE_BASE_URL=http://127.0.0.1:8788 OPENCODE_LIVE_MODEL_ID=opencode/gpt-5-nano PYTHONPATH=. pytest tests/opencode_server_client/test_opencode_server_client_live.py -q`
- Date/Time: 2026-02-19 00:18:56 EET
- Result: Pass (2 passed, 1 warning)

## Known Gaps / Follow-ups
- Live tests require opt-in env and local OpenCode daemon:
  - `OPENCODE_LIVE_TEST=1`
  - Optional `OPENCODE_LIVE_FULL_TASK=1`
  - Optional `OPENCODE_LIVE_MODEL_ID=<provider/model>`
  - Optional `APPS_CODING_AGENT_OPENCODE_BASE_URL=http://127.0.0.1:8788`
- Live full-task test still depends on model/tool reliability; the test mitigates intermittent misses with two attempts before failing.
