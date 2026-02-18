# Coding Agent Runtime Refactor Implementation Tracker

Last Updated: 2026-02-18

## Scope
Implements first-pass backend cutover from legacy builder chat runtime to `/admin/apps/{app_id}/coding-agent/*` APIs using platform runtime primitives.

## Phase Status
- Phase 1 (durability + run metadata): completed
- Phase 2 (coding toolpack + policy): completed
- Phase 3 (coding-agent backend APIs + stream mapping): completed
- Phase 4 (auto-apply revision + checkpoint restore): completed
- Phase 5 (frontend contract migration): completed
- Phase 6 (legacy endpoint/module deletion): completed
- Phase 7 (stabilization + backend test migration): in progress
- Hardening Phase 1 (must-ship correctness): completed (2026-02-18)
- Hardening Phase 2 (deeper runtime/e2e durability gaps): pending
- OpenCode A/B (dev/staging, fail-closed): implemented
- Remaining: broader runtime hardening, expanded coding-agent tool/runtime assertions, deeper frontend event assertions

## Implemented Changes
- Added durable LangGraph checkpointer: `backend/app/agent/execution/durable_checkpointer.py`
- Switched `AgentExecutorService` to durable checkpointer.
- Extended `AgentRun` linkage fields for coding-agent app/revision context.
- Added Alembic migration:
  - `backend/alembic/versions/5d7e9b1c2a3f_add_coding_agent_linkage_fields_to_agent_runs.py`
- Added coding-agent tooling/profile/runtime services:
  - `backend/app/services/published_app_coding_agent_tools.py`
  - `backend/app/services/published_app_coding_agent_profile.py`
  - `backend/app/services/published_app_coding_agent_runtime.py`
- Added new coding-agent routes:
  - `backend/app/api/routers/published_apps_admin_routes_coding_agent.py`
- Added run-scoped model-selection contract for coding-agent runs:
  - `POST /admin/apps/{app_id}/coding-agent/runs` accepts optional `model_id` (`Auto` when omitted/null)
  - run responses now include `requested_model_id` and `resolved_model_id`
  - unavailable selected model now fails fast with `400` + `CODING_AGENT_MODEL_UNAVAILABLE`
- Added run-level model pinning persistence:
  - migration `backend/alembic/versions/8e4f2a1b9c0d_add_run_level_model_pinning_to_agent_runs.py`
  - ORM fields on `AgentRun`: `requested_model_id`, `resolved_model_id`
- Added compile-time run-scoped model override:
  - `AgentExecutorService` applies pinned `resolved_model_id` onto graph nodes (`agent`/`llm`/`classify`) at execution time
  - execution no longer depends on mutable shared profile defaults once run is created
- Added non-breaking OpenCode engine A/B path behind existing coding-agent API/SSE contracts:
  - create-run request supports `engine` (`native` default, `opencode` optional)
  - run responses include `execution_engine`; `agent_runs` now stores `execution_engine` + optional `engine_run_ref`
  - runtime service routes per-run execution to `native` or `opencode` engine adapters
  - OpenCode engine preflight enforces fail-closed behavior with deterministic errors:
    - `CODING_AGENT_ENGINE_UNAVAILABLE`
    - `CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME`
  - OpenCode cancellation uses best-effort upstream cancel and fails closed when cancellation cannot be confirmed
  - added adapter/client modules:
    - `backend/app/services/published_app_coding_agent_engines/base.py`
    - `backend/app/services/published_app_coding_agent_engines/native_engine.py`
    - `backend/app/services/published_app_coding_agent_engines/opencode_engine.py`
    - `backend/app/services/opencode_server_client.py`
- Added strict pre-dispatch required-field validation for coding-agent function tools:
  - deterministic validation failure envelope: `TOOL_INPUT_VALIDATION_FAILED` + `fields`
  - builder policy/contract exceptions normalized into structured tool failure envelopes (`code/message/field`)
- Added builder per-run model picker:
  - composer now shows `Auto` + active chat models from `/models`
  - selected model is sent as `model_id` per message/run
- Removed legacy modules/endpoints:
  - deleted `published_apps_admin_routes_chat.py`
  - deleted `published_apps_admin_builder_agentic.py`
  - deleted `published_apps_admin_builder_model.py`
  - deleted `published_apps_admin_builder_patch.py`
  - removed routes `/builder/chat/stream`, `/builder/checkpoints`, `/builder/undo`, `/builder/revert-file`
- Removed obsolete backend feature flag code paths for legacy builder chat toggles.
- Migrated backend test coverage away from removed legacy builder chat APIs:
  - trimmed `backend/tests/published_apps/test_builder_revisions.py` to non-legacy builder revision flows
  - added `backend/tests/coding_agent_api/test_run_lifecycle.py`
  - added `backend/tests/coding_agent_checkpoints/test_checkpoint_restore.py`
  - updated `backend/tests/published_apps/test_admin_apps_publish_rules.py` to assert environment-derived publish URLs
  - added feature `test_state.md` files:
    - `backend/tests/coding_agent_api/test_state.md`
    - `backend/tests/coding_agent_checkpoints/test_state.md`
- Migrated frontend builder workspace contract to coding-agent APIs:
  - replaced legacy `/builder/chat/stream` call with `/coding-agent/runs` + `/coding-agent/runs/{run_id}/stream`
  - send prior user/assistant turns as `messages` on run creation for multi-turn conversational continuity
  - replaced undo flow (`/builder/undo`) with checkpoint restore (`/coding-agent/checkpoints` + `/restore`)
  - updated frontend SSE handling to coding-agent event envelope (`run.accepted`, `assistant.delta`, `tool.*`, `revision.created`, `checkpoint.created`, `run.completed`, `run.failed`)
  - removed frontend source references to deleted legacy builder chat/checkpoint/undo/revert endpoints
- Hardened assistant response behavior for regular chat-like UX:
  - added coding-agent profile instruction requiring natural-language replies for every user message
  - added explicit file-tool argument contract in profile instructions (`path`, `from_path`, `to_path`) to reduce malformed tool calls
  - added runtime fallback emission of `assistant.delta` from final run output when token stream is empty
  - added prompt-aware runtime fallback text for greeting/help turns when final model output is missing
  - added executor-level fallback turn to force a plain-text completion when an iteration ends with no tool call and no text
- Fixed run persistence and latency regressions in coding-agent tool execution:
  - added `ensure_active_session` path in draft-dev runtime service so tool calls do not full-sync DB files into sandbox on every invocation
  - switched coding-agent tool context bootstrap to `ensure_active_session` to avoid overwriting in-progress sandbox edits
  - switched auto-apply checkpoint flow to snapshot from active sandbox session without pre-syncing old revision files
  - reduced coding-agent profile defaults from `max_tool_iterations=24`/`tool_timeout_s=360` to env-overridable `8`/`120` for faster simple edit loops
  - normalized tool input aliases for path-bearing calls (`file_path`/`filePath`/`fromPath`/`toPath` etc.) in the reasoning executor + coding-agent tool adapters to prevent repeated `BUILDER_PATCH_POLICY_VIOLATION` (`File path is required`) failures
  - expanded path alias resolution to nested payload wrappers (`input`/`args`/`parameters`/`payload`) in coding-agent tool adapters so path-bearing calls do not fail when model outputs nested argument shapes
  - added JSON-string argument decoding for tool payload wrappers (`value`/`args`/`input`/`parameters`/`payload`) across reasoning coercion + tool execution so path-bearing calls work even when tool arguments arrive as serialized JSON strings
  - merged function-tool `args` payloads with top-level execution context in `ToolNodeExecutor` so runtime metadata (for example `run_id`) is preserved while still honoring nested tool arguments
  - made draft session prewarm in coding-agent `create_run` best-effort: runtime bootstrap failures now log a warning and no longer fail run creation
  - added API regression coverage for create-run behavior when draft session prewarm raises an environment/runtime error
- Reduced UI lifecycle noise in builder agent panel:
  - removed `Run accepted` / `Run complete` timeline cards from user-facing stream rendering
  - render assistant replies as normal chat messages
  - hide `revision.created` / `checkpoint.created` / diagnostic payload blocks from chat timeline
  - replaced post-run full `loadState` call with silent builder state refresh to avoid whole-page loading flicker after each assistant turn
  - render tool calls as dedicated rows (running shimmer, completed/failed persisted states) without raw payload JSON
- Refined builder coding-agent panel UX to mirror playground/execution chat ergonomics:
  - fixed chat scroll behavior by aligning panel container hierarchy to `min-h-0` + flex/overflow patterns used in playground chat workspace
  - upgraded panel visual hierarchy to a Cursor-like shell (session status strip, tighter message cards, cleaner separation between stream and composer)
  - rendered tool/event timeline rows with Chain-of-Thought blocks for clearer step-by-step execution visibility
  - render `assistant.delta` content incrementally (live partial text) instead of waiting for stream completion
- Fixed coding-agent SSE framing bug that prevented client parsing of stream envelopes:
  - corrected `/coding-agent/runs/{run_id}/stream` formatter to emit real newline delimiters (`\n\n`) instead of escaped literals (`\\n\\n`)
  - corrected heartbeat prelude framing to real SSE comment delimiters
  - expanded API test coverage to assert streamed `run.accepted`/`run.completed` `data:` frames are present in the response body
- Fixed streaming finalize failure on detached ORM instances:
  - `stream_run_events` now re-loads `AgentRun` by `run_id` before finalize/commit/error paths instead of calling `refresh(run)` on a potentially detached instance
  - added regression coverage for detached run instance handling in coding-agent API lifecycle tests
- Cursor-style panel refinement pass:
  - removed top "Agent session" strip from builder panel
  - replaced panel scroll region with explicit `overflow-y-auto` container + manual "scroll to latest" affordance for deterministic scrolling
  - updated active thinking block to `ChainOfThought` shimmer style (`Thinking...`) aligned with playground execution UX
  - refined composer to Cursor-like prompt affordances and updated placeholder (`Plan, @ for context, / for commands`)
- Minimalist panel pass (follow-up):
  - switched builder panel back to AI elements `Conversation` + `ConversationContent` + `ConversationScrollButton` composition
  - removed extra message/input separators and heavy card borders to match a lighter Cursor-like feel
  - changed active thinking indicator from block card to lightweight shimmering inline `Thinking...` text
  - moved composer outside the conversation scroll container so the input stays pinned while messages scroll
- Scroll containment hardening (apps builder shell + workspace):
  - switched admin apps-builder route shell to viewport-bounded `h-dvh min-h-0` contract
  - replaced workspace root `h-screen` with `h-dvh min-h-0` and added missing `min-h-0` on intermediate flex containers
  - added overflow clamp on coding-agent aside so timeline growth cannot expand document height
  - added frontend regression test asserting viewport-bounded root/agent-panel class contract
- Patch-first runtime refactor (SOTA hardening tranche):
  - added unified-diff patch engine module `backend/app/services/published_app_draft_dev_patching.py` with strict hunk-context matching and atomic transaction semantics
  - added fallback parser for `*** Begin Patch` / `*** Update File` payload format so non-unified-diff patch calls are applied instead of failing with `PATCH_PARSE_FAILED`
  - added local runtime APIs:
    - `read_file_range` (line-range + context + byte-budget reads)
    - `workspace_index` (path/size/hash/language/symbol-outline metadata)
    - `apply_patch` (structured failure envelope with `failures[]`, `code`, `summary`, and revision tokens)
  - added runtime client parity methods for embedded/remote controllers:
    - `read_file_range`
    - `workspace_index`
    - `apply_patch`
  - added coding-agent toolpack migration:
    - new tools: `coding_agent_read_file_range`, `coding_agent_workspace_index`, `coding_agent_collect_context`, `coding_agent_apply_patch`
    - deprecated `coding_agent_write_file`; disabled by default unless `APPS_CODING_AGENT_ENABLE_LEGACY_WRITE_FILE=1`
    - patch failure path now auto-fetches recommended line windows for context refresh (`refresh_windows`)
    - patch success path now includes verification planning metadata (`verification_plan`) and optional auto-verify execution behind `APPS_CODING_AGENT_AUTO_VERIFY_PATCH=1`
  - added stream diagnostics enrichment for patch failures in `tool.failed` envelopes (`patch_failure_count`, `recommended_refresh`, `patch_code`)
  - added message-budget compaction in coding-agent run creation (`APPS_CODING_AGENT_MESSAGE_BUDGET_CHARS`) for context pressure control
  - updated architecture map to include `backend/app/services/published_app_draft_dev_patching.py`
  - expanded backend tests:
    - new feature directory: `backend/tests/coding_agent_runtime_editing/`
    - new tests: `backend/tests/coding_agent_runtime_editing/test_patch_runtime.py`
    - extended tool payload tests for patch/range required fields and alias resolution
    - extended coding-agent API tests for patch-failure diagnostics mapping

## Commands Run
1. `python3 -m compileall backend/app backend/alembic/versions/5d7e9b1c2a3f_add_coding_agent_linkage_fields_to_agent_runs.py`
- Result: pass

2. `PYTHONPATH=backend python3 - <<'PY' ...` (router import + route presence check)
- Result: pass
- Confirmed: `/admin/apps/{app_id}/coding-agent/*` routes registered
- Confirmed: legacy `/admin/apps/{app_id}/builder/chat/stream` and removed builder mutation routes are not registered

3. `PYTHONPATH=backend pytest -q backend/tests/published_apps/test_builder_revisions.py`
- Result: pass (7 passed)

4. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api`
- Result: pass (4 passed)

5. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_checkpoints`
- Result: pass (2 passed)

6. `PYTHONPATH=backend pytest -q backend/tests/published_apps`
- Result: pass (31 passed)

7. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 16 tests)

8. `cd frontend-reshet && npm test -- src/__tests__/published_apps --runInBand`
- Result: pass (5 suites, 21 tests)

9. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api`
- Result: pass (6 passed)

10. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 17 tests)

11. `PYTHONPATH=backend pytest -q backend/tests/published_apps backend/tests/coding_agent_checkpoints`
- Result: pass (35 passed)

12. `PYTHONPATH=backend pytest -q backend/tests/agent_builder_nodes backend/tests/coding_agent_api`
- Result: pass (5 passed, 7 skipped)

13. `PYTHONPATH=backend pytest -q backend/tests/published_apps backend/tests/coding_agent_checkpoints backend/tests/coding_agent_api`
- Result: pass (41 passed)

14. `cd frontend-reshet && npm test -- src/__tests__/published_apps --runInBand`
- Result: pass (5 suites, 22 tests)

15. `cd frontend-reshet && npm run build`
- Result: fail in sandbox environment due blocked external Google Fonts fetch (`Geist`, `Geist Mono`)

16. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 18 tests)

17. `cd frontend-reshet && npm test -- src/__tests__/published_apps --runInBand`
- Result: pass (5 suites, 23 tests)

18. `PYTHONPATH=backend pytest -q backend/tests/published_apps backend/tests/coding_agent_checkpoints backend/tests/coding_agent_api`
- Result: pass (41 passed)

19. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api backend/tests/coding_agent_checkpoints`
- Result: pass (8 passed)

20. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 18 tests)

21. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Result: pass (6 passed)

22. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 19 tests)

23. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api backend/tests/coding_agent_checkpoints`
- Result: pass (8 passed)

24. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 19 tests)

25. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Result: pass (7 passed)

26. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 19 tests)

27. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api backend/tests/coding_agent_checkpoints`
- Result: pass (9 passed)

28. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 19 tests)

29. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 19 tests)

30. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 20 tests)

31. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 21 tests)

32. `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_function_tool_execution.py`
- Result: pass (5 passed)

33. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Result: pass (7 passed)

34. `python3 -m compileall backend/app/agent/executors/standard.py backend/app/services/published_app_coding_agent_tools.py backend/tests/tool_execution/test_reasoning_tool_input_aliases.py`
- Result: pass

35. `python3 -m compileall backend/app/services/published_app_coding_agent_profile.py`
- Result: pass

36. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 23 tests)

37. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Result: pass (7 passed)

38. `python3 -m compileall backend/app/services/published_app_coding_agent_profile.py backend/app/services/published_app_coding_agent_runtime.py backend/app/api/routers/published_apps_admin_routes_coding_agent.py`
- Result: pass

39. `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py`
- Result: pass (9 passed)

40. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Result: pass (7 passed)

41. `python3 -m compileall backend/app/services/published_app_coding_agent_tools.py backend/app/agent/executors/standard.py backend/app/agent/executors/tool.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_function_tool_execution.py`
- Result: pass

42. `PYTHONPATH=backend pytest -q backend/tests/tool_execution/test_reasoning_tool_input_aliases.py backend/tests/tool_execution/test_function_tool_execution.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py`
- Result: pass (12 passed)

43. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Result: pass (7 passed)

44. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py backend/tests/tool_execution/test_function_tool_execution.py`
- Result: pass (17 passed)

45. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx -t "model selector|selected model_id|model is unavailable" --runInBand`
- Result: pass (3 passed, 24 skipped)

46. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 27 tests)

47. `python3 -m compileall backend/app/services/published_app_draft_dev_patching.py backend/app/services/published_app_draft_dev_local_runtime.py backend/app/services/published_app_draft_dev_runtime_client.py backend/app/services/published_app_coding_agent_tools.py backend/app/services/published_app_coding_agent_profile.py backend/app/services/published_app_coding_agent_runtime.py backend/tests/coding_agent_runtime_editing/test_patch_runtime.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py backend/tests/coding_agent_api/test_run_lifecycle.py`
- Result: pass

48. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_runtime_editing/test_patch_runtime.py backend/tests/tool_execution/test_coding_agent_tool_path_resolution.py backend/tests/coding_agent_api/test_run_lifecycle.py`
- Result: pass (26 passed)

49. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_runtime_editing/test_patch_runtime.py`
- Result: pass (4 passed)

50. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_runtime_editing/test_patch_runtime.py`
- Result: pass (5 passed)

47. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py backend/tests/tool_execution/test_function_tool_execution.py`
- Result: pass (17 passed)

48. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py backend/tests/tool_execution`
- Result: pass (32 passed)

49. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api/test_run_lifecycle.py`
- Result: pass (12 passed)

## Known Gaps
- Coding-agent stream tests currently validate generator execution/headers in API tests; deeper deterministic envelope assertions should be added in runtime-focused tests.
- Frontend workspace tests validate coding-agent run creation/stream usage and checkpoint restore flow, but can still add richer assertions for tool payload semantics and failure envelopes.
- Tool output semantics are functional but still need production-level tightening for richer diagnostics and cancellation propagation.
- Durable checkpointer is file-backed in this pass; a database-backed saver can be added later for stronger multi-instance durability.
- Full visual browser E2E (real DOM screenshot-level validation) is still not wired as a first-class automated suite in this repo.
- Running the full backend server in this sandbox is blocked by external lifecycle dependencies (notably Pinecone DNS/connectivity), so live HTTP verification here depends on test-client coverage unless those integrations are disabled.
