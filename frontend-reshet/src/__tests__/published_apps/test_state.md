# Published Apps Frontend Tests

Last Updated: 2026-04-14

## Scope
Frontend coverage for published-apps admin and public runtime surfaces outside the new versions module.

## Test Files
- `frontend-reshet/src/__tests__/published_apps/apps_admin_page.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/apps_builder_file_filter.test.ts`
- `frontend-reshet/src/__tests__/published_apps/chat_thread_tabs.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/chat_panel_behaviors.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/chat_history_timeline.test.ts`
- `frontend-reshet/src/__tests__/published_apps/chat_model_path_parsing.test.ts`
- `frontend-reshet/src/__tests__/published_apps/coding_agent_stream_speed.test.ts`
- `frontend-reshet/src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx`

## Key Scenarios Covered
- Apps admin page list/create/update behavior.
- Apps admin page inline stats: fetch, display, loading skeleton, error degradation, date range switching.
- Builder file-filter and blocked path rules.
- Chat timeline/thread rendering behaviors.
- Chat panel shimmer cutoff and scroll-fade activation.
- Chat footer chrome can render the canonical context-window indicator without pulling runtime-only `tokenlens` into tests.
- Coding-agent stream speed/coalescing expectations.
- Preview auth token channel updates and iframe src stability across token refreshes.
- Preview keeps the iframe mounted during same-session transient pending/recovering states instead of immediately blanking it.
- Preview stages same-session route changes behind the current iframe and swaps only after the new document loads.
- Preview cold-boot loading now renders explicit staged progress instead of a generic blank spinner.
- Preview keeps the full warmup overlay visible until the iframe is actually usable, instead of disappearing as soon as the iframe node is mounted.

## Last Run
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

## Known Gaps / Follow-ups
- Workspace versions-first flows moved to `frontend-reshet/src/__tests__/apps_builder_versions/`.
- Add explicit tests for versions panel integration inside `AppsBuilderWorkspace`.
