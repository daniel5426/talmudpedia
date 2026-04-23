# Apps Builder Versions Test State

Last Updated: 2026-04-23

## Scope
Frontend versions-first workflow in Apps Builder workspace.

## Test Files
- `frontend-reshet/src/__tests__/apps_builder_versions/versions_hook.test.tsx`

## Key Scenarios Covered
- Versions list and selected version loading via `/versions` + `/versions/{id}`.
- Hook service mocks include `/versions/{id}/preview-runtime` returning a bootstrap-ready `preview_url`.
- Restore action uses `/versions/{id}/restore` and refresh callbacks.
- Publish action uses `/versions/{id}/publish` and job polling endpoint.
- Legacy revision/checkpoint service methods are removed from the client surface.

## Last Run
- Command: `cd /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet && ./node_modules/.bin/jest --runInBand src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx src/__tests__/apps_builder_versions/versions_hook.test.tsx`
- Date: 2026-04-23 Asia/Hebron
- Result: PASS (`2 suites, 10 tests`)

## Known Gaps / Follow-ups
- Add chat-panel integration tests for version selection persistence and inspect-mode preview switching.
- Add workspace-level tests to verify version inspect mode exits automatically before new run submission.
