# Published Apps Frontend Tests

Last Updated: 2026-03-01

## Scope
Frontend coverage for published-apps admin and public runtime surfaces outside the new versions module.

## Test Files
- `frontend-reshet/src/__tests__/published_apps/apps_admin_page.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/apps_builder_file_filter.test.ts`
- `frontend-reshet/src/__tests__/published_apps/chat_thread_tabs.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/chat_history_timeline.test.ts`
- `frontend-reshet/src/__tests__/published_apps/chat_model_path_parsing.test.ts`
- `frontend-reshet/src/__tests__/published_apps/coding_agent_stream_speed.test.ts`
- `frontend-reshet/src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx`

## Key Scenarios Covered
- Apps admin page list/create/update behavior.
- Builder file-filter and blocked path rules.
- Chat timeline/thread rendering behaviors.
- Coding-agent stream speed/coalescing expectations.
- Preview auth token channel updates.

## Last Run
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps/chat_history_timeline.test.ts`
- Date: 2026-03-01
- Result: Pending

## Known Gaps / Follow-ups
- Workspace versions-first flows moved to `frontend-reshet/src/__tests__/apps_builder_versions/`.
- Add explicit tests for versions panel integration inside `AppsBuilderWorkspace`.
