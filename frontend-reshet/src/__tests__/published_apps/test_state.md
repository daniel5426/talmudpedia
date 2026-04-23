# Published Apps Frontend Tests

Last Updated: 2026-04-23

## Scope
Frontend coverage for published-apps admin and public runtime surfaces outside the new versions module.

## Test Files
- `frontend-reshet/src/__tests__/published_apps/apps_admin_page.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/apps_builder_file_filter.test.ts`
- `frontend-reshet/src/__tests__/published_apps/chat_thread_tabs.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/chat_panel_behaviors.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/chat_session_hydration.test.ts`
- `frontend-reshet/src/__tests__/published_apps/chat_history_timeline.test.ts`
- `frontend-reshet/src/__tests__/published_apps/chat_model_path_parsing.test.ts`
- `frontend-reshet/src/__tests__/published_apps/coding_agent_stream_speed.test.ts`
- `frontend-reshet/src/__tests__/published_apps/coding_agent_stream_url.test.ts`
- `frontend-reshet/src/__tests__/published_apps/published_runtime_service.test.ts`
- `frontend-reshet/src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx`

## Key Scenarios Covered
- Apps admin page list/create/update behavior.
- Apps admin page inline stats: fetch, display, loading skeleton, error degradation, date range switching.
- Apps admin page reloads cleanly when the active project changes, so stale project data does not survive a switch.
- Builder file-filter and blocked path rules.
- Chat timeline/thread rendering behaviors.
- Post-idle history hydration does not overwrite a newer in-flight send with stale previous-turn history.
- Chat panel shimmer cutoff and scroll-fade activation.
- Chat footer chrome can render the canonical context-window indicator without pulling runtime-only `tokenlens` into tests.
- Coding-agent session stream speed/per-event rendering expectations on the new session SSE contract.
- Coding-agent stream consumer ignores user text-part echoes and assistant shell-only `message.updated` frames, so the panel does not briefly render the prompt as assistant output or create a blank assistant row before real content arrives.
- Coding-agent direct SSE URL resolution preserves the browser's active loopback hostname, preventing local auth/cookie mismatches between `localhost` and `127.0.0.1`.
- Coding-agent stream consumer rejects non-`text/event-stream` responses instead of silently retrying forever on HTML/auth/error bodies.
- Chat history timeline rebuilds tool rows from official message parts instead of legacy run events.
- Preview relies on the server-provided bootstrap URL without a client-side auth-token channel, while keeping iframe src stable across same-session route changes.
- Public runtime service omits ambient browser cookies and disables caching for auth and bearer-stream fetches.
- Preview keeps the iframe mounted during same-session transient pending/recovering states instead of immediately blanking it.
- Preview stages same-session route changes behind the current iframe and swaps only after the new document loads.
- Preview cold-boot loading now renders explicit staged progress instead of a generic blank spinner.
- Preview keeps the full warmup overlay visible until the iframe is actually usable, instead of disappearing as soon as the iframe node is mounted.

## Last Run
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet && npm test -- --runTestsByPath src/__tests__/published_apps/apps_admin_page.test.tsx --watch=false`
- Date: 2026-04-21 Asia/Hebron
- Result: PASS (`1 suite, 7 tests`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && pnpm --dir frontend-reshet test -- --runInBand src/__tests__/published_apps/chat_history_timeline.test.ts src/__tests__/published_apps/coding_agent_stream_speed.test.ts src/__tests__/published_apps/coding_agent_stream_url.test.ts src/__tests__/published_apps/chat_session_hydration.test.ts`
- Date: 2026-04-18 21:52 EEST
- Result: PASS (`4 suites, 11 tests`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet && pnpm test -- --runInBand src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/auth_session_bootstrap/auth_refresher.test.tsx src/__tests__/published_apps/published_runtime_service.test.ts`
- Date: 2026-04-19 Asia/Hebron
- Result: PASS (`3 suites, 5 tests`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && pnpm --dir frontend-reshet test -- --runInBand src/__tests__/published_apps/coding_agent_stream_speed.test.ts src/__tests__/published_apps/coding_agent_stream_url.test.ts`
- Date: 2026-04-18 21:52 EEST
- Result: PASS (`2 suites, 6 tests`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet && pnpm test -- --runInBand src/__tests__/published_apps/chat_history_timeline.test.ts src/__tests__/published_apps/coding_agent_stream_speed.test.ts`
- Date: 2026-04-17 Asia/Hebron
- Result: PASS (`2 suites, 5 tests`)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia && pnpm --dir frontend-reshet test -- --runInBand src/__tests__/published_apps/coding_agent_stream_speed.test.ts src/__tests__/published_apps/coding_agent_stream_url.test.ts`
- Date: 2026-04-17 Asia/Hebron
- Result: PASS (`2 suites, 5 tests`)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/published_apps/chat_panel_behaviors.test.tsx`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`4 passed`)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx`
- Date: 2026-03-16
- Result: Pass
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx --watch=false`
- Date: 2026-03-17
- Result: PASS (3 passed)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx`
- Date: 2026-04-14 Asia/Hebron
- Result: PASS (`1 suite, 4 tests`)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx`
- Date: 2026-04-14 18:31 EEST
- Result: PASS (`1 suite, 5 tests`)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx`
- Date: 2026-04-15 00:19 EEST
- Result: PASS (`1 suite, 6 tests`)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps/apps_admin_page.test.tsx --watch=false`
- Date: 2026-03-22
- Result: PASS (7 passed — 3 existing + 4 new stats tests)
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/published_apps/apps_admin_page.test.tsx src/__tests__/published_apps/published_runtime_service.test.ts src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/auth_session_bootstrap/admin_layout_auth_gate.test.tsx src/__tests__/auth_session_bootstrap/auth_refresher.test.tsx src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/settings_projects/settings_projects_service.test.ts src/__tests__/settings_people_permissions/settings_people_permissions_service.test.ts src/__tests__/settings_people_permissions/settings_people_permissions_dialogs.test.tsx src/__tests__/settings_shell/settings_shell.test.tsx`
- Date: 2026-04-20 23:17 EEST
- Result: PASS (`11 suites, 31 tests`)

## Known Gaps / Follow-ups
- Workspace versions-first flows moved to `frontend-reshet/src/__tests__/apps_builder_versions/`.
- No focused hook-level test covers the full `useAppsBuilderChat` session lifecycle yet; current frontend coverage is still stream/history focused.
- Add explicit tests for versions panel integration inside `AppsBuilderWorkspace`.

## 2026-04-21 tenant-to-organization validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/admin_threads/threads_table.test.ts src/__tests__/admin_threads/admin_thread_page.test.tsx src/__tests__/admin_monitoring/users_table_monitoring.test.tsx src/__tests__/artifacts_admin/artifact_test_panel.test.tsx src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/config_panel_artifact_contracts.test.tsx src/__tests__/pipeline_tool_bindings/pipeline_tool_settings_page.test.tsx`
- Result: PASS (`11 suites passed, 25 tests passed`)

## 2026-04-23 unified preview auth contract
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet && ./node_modules/.bin/jest --runInBand src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx src/__tests__/apps_builder_versions/versions_hook.test.tsx`
- Date: 2026-04-23 Asia/Hebron
- Result: PASS (`2 suites, 10 tests`)

## 2026-04-23 apps-builder reconnect quieting
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet && ./node_modules/.bin/jest --runInBand src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx`
- Date: 2026-04-23 Asia/Hebron
- Result: PASS (`1 suite, 6 tests`). Same-session reconnecting preview states now keep the iframe mounted without showing the small reconnect overlay.
