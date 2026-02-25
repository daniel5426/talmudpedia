Last Updated: 2026-02-25

## Scope
- OpenCode server client transport compatibility for coding-agent engine runs.
- Official API mode (`/global/health`, `/global/event`, `/session*`).
- Legacy API fallback mode (`/health`, `/v1/runs*`).

## Test Files
- `backend/tests/opencode_server_client/test_opencode_server_client.py`
- `backend/tests/opencode_server_client/test_opencode_server_client_live.py`

## Key Scenarios Covered
- Official mode unwraps `{success,data}` and supports `prompt_async` with fallback to `POST /session/{id}/message`.
- Official mode never calls OpenCode MCP registration (`/mcp`) for selected-agent contract access.
- OpenCode run startup seeds project-local custom tools into workspace `.opencode/tools/*` and seeds run-scoped contract context in `.cache/opencode/selected_agent_contract.json`.
- Sandbox seeding is cached per sandbox/workspace: unchanged bootstrap files are not rewritten on every run.
- Volatile contract metadata (`generated_at`) is ignored in context hashing so no-op runs do not rewrite context files.
- Contract context seeding refreshes only when selected-agent contract content changes.
- Sandbox-controller mode seeds custom tools via sandbox file APIs before OpenCode start and fails closed on seed-write failures.
- Host mode fails closed when `workspace_path` is missing/invalid for custom-tool bootstrap.
- Global event stream translation emits incremental `assistant.delta` tokens and tool lifecycle events (`tool.started` / `tool.completed` / `tool.failed`).
- Global event parsing preserves early tool events even before assistant message-role metadata lands.
- Global event `message.updated` payloads are now parsed for incremental assistant text/tool state, including fallback text-diff extraction when `message.part.delta` is absent.
- Session `idle` no longer force-completes runs by default; streams now continue when assistant text is followed by later tool calls in the same run.
- Reasoning parts are filtered out from user-visible assistant deltas.
- Incremental text offset tracking prevents duplicate text when `/global/event` and `/session/{id}/message` overlap.
- Official global-event streaming can settle to terminal completion without explicit `session.idle` when assistant text is complete and no tools are running.
- Official global-event streaming now treats `session.status(type=idle)` as canonical completion signal when latest assistant finish is terminal (`finish != tool-calls|unknown`).
- Idle handling does not prematurely complete mid-run tool continuations (`finish=tool-calls` remains non-terminal).
- Recoverable tool-step errors in earlier assistant turns no longer force terminal run failure when a later assistant turn succeeds.
- Snapshot polling fallback remains compatible (empty response recovery, wrapped payloads, missing `parentID`, read-timeout recovery).
- Session creation includes workspace external-directory permission rules.
- Missing assistant text still fails closed with deterministic diagnostics.
- Host/API mode question answers and cancel requests ignore `sandbox_id` hints and stay on direct OpenCode API paths (prevents controller recursion when host mode is forced).
- Live roundtrip and live full-task edit flows are validated against a real OpenCode daemon.

## Last Run
- Command: `pytest -q backend/tests/opencode_server_client/test_opencode_server_client.py -k "global_event_stream_keeps_running_after_session_idle_text_before_tool or global_event_stream_settles_without_session_idle or global_event_stream_completes_from_session_status_idle or closed_no_terminal_recovers_via_snapshot_polling or start_run_buffers_assistant_events"`
- Date/Time: 2026-02-25
- Result: Pass (5 passed, 28 deselected, 1 warning)
- Command: `pytest -q backend/tests/opencode_server_client/test_opencode_server_client.py -k "global_event_stream or closed_no_terminal or auto_approves_permission_asked or settles_without_session_idle"`
- Date/Time: 2026-02-25 21:25 EET
- Result: Pass (7 passed, 25 deselected, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py::test_host_mode_answer_question_ignores_sandbox_id_and_uses_api tests/opencode_server_client/test_opencode_server_client.py::test_host_mode_cancel_ignores_sandbox_id_and_uses_api tests/sandbox_controller/test_dev_shim.py::test_dev_shim_opencode_question_answer tests/coding_agent_api/test_v2_api.py::test_v2_answer_question_endpoint`
- Date/Time: 2026-02-24
- Result: Pass (4 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py::test_official_mode_global_event_stream_emits_deltas_from_message_updated_payload`
- Date/Time: 2026-02-24
- Result: Pass (1 passed, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_v2_api.py::test_v2_stream_emits_assistant_delta_per_chunk_and_old_route_is_404`
- Date/Time: 2026-02-24
- Result: Pass (1 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/coding_agent_api/test_terminal_stream_completion.py tests/coding_agent_api/test_opencode_apply_patch_recovery.py tests/opencode_server_client/test_opencode_server_client.py`
- Date/Time: 2026-02-22
- Result: Pass (32 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py`
- Date/Time: 2026-02-22
- Result: Pass (26 passed, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py`
- Date/Time: 2026-02-22
- Result: Pass (25 passed, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py`
- Date/Time: 2026-02-21
- Result: Pass (24 passed, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py`
- Date/Time: 2026-02-21
- Result: Pass (23 passed, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py tests/sandbox_controller/test_draft_dev_runtime_client_stream.py`
- Date/Time: 2026-02-19 22:35 UTC
- Result: Pass (25 passed, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py`
- Date/Time: 2026-02-19 22:17 UTC
- Result: Pass (21 passed, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/opencode_server_client/test_opencode_server_client.py`
- Date/Time: 2026-02-19 22:01 UTC
- Result: Pass (20 passed, 1 warning)
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
