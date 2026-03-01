# Apps Builder Versions Test State

Last Updated: 2026-03-01

## Scope
Frontend versions-first workflow in Apps Builder workspace.

## Test Files
- `frontend-reshet/src/__tests__/apps_builder_versions/versions_hook.test.tsx`

## Key Scenarios Covered
- Versions list and selected version loading via `/versions` + `/versions/{id}`.
- Hook service mocks include `/versions/{id}/preview-runtime` integration path.
- Restore action uses `/versions/{id}/restore` and refresh callbacks.
- Publish action uses `/versions/{id}/publish` and job polling endpoint.
- Legacy revision/checkpoint service methods are removed from the client surface.

## Last Run
- Command: `cd frontend-reshet && npm test -- --runTestsByPath src/__tests__/apps_builder_versions/versions_hook.test.tsx --watch=false`
- Date: 2026-03-01
- Result: Pass (4 passed)

## Known Gaps / Follow-ups
- Add chat-panel integration tests for version selection persistence and inspect-mode preview switching.
- Add workspace-level tests to verify version inspect mode exits automatically before new run submission.
