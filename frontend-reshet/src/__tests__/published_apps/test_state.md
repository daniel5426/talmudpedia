# Published Apps Frontend Tests

Last Updated: 2026-02-16

## Scope
Frontend coverage for:
- Admin Apps management page behavior.
- Builder workspace behavior (`Preview | Config`, template reset confirm, builder patch apply/save).
- Builder draft-dev preview behavior (session ensure/sync/heartbeat + sandbox iframe URL usage).
- Async publish-job flow from workspace publish action.
- Published runtime redirect behavior.
- Published login flow token persistence and auth template rendering.
- Published runtime error handling when runtime descriptor cannot be resolved.

## Test Files
- `frontend-reshet/src/__tests__/published_apps/apps_admin_page.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/apps_builder_workspace.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_auth_templates.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_runtime_gate.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_auth_flows.test.tsx`

## Key Scenarios Covered
- Apps admin page loads existing apps and submits create payload.
- Apps admin create modal supports frontend template + auth template selection and builder-route redirect on create.
- Builder workspace renders tabs, persists draft revision saves, confirms template overwrite, and applies streamed patch ops to revision save.
- Builder workspace supports `Config` section navigation (`Overview | Users | Domains | Code`).
- Overview section save path is covered for branding/visibility/auth template payloads.
- Users section list/block action flow is covered.
- Domains section list/create request flow is covered.
- Builder workspace renders execution-style agent timeline cards from typed stream events (`status`, `tool_started`, `tool_completed`, `tool_failed`, `file_changes`, `checkpoint_created`).
- Builder workspace supports quick actions for `Undo Last Run` and `Revert File`.
- Builder code tab renders a hierarchical folder/file tree (not flat paths) and supports folder expand/collapse interactions.
- Builder code tab auto-expands ancestor folders when the selected file is nested.
- Builder code tab maps `index.html` to Monaco `html` language and sets builder-only validation decoration suppression.
- Builder workspace ensures draft-dev session on preview and uses sandbox `preview_url` for iframe rendering.
- Builder workspace syncs draft files via draft-dev sync API without creating revisions per keystroke.
- Publish action uses async publish-job contract (`publish` + `getPublishJobStatus`).
- Publish action surfaces immediate failed publish-job responses without entering status polling.
- Open App now falls back to published-revision preview runtime proxy for local `*.apps.localhost` domains.
- Runtime page redirects directly to static published runtime URL via `/public/apps/{slug}/runtime`.
- Login stores app-scoped bearer token and redirects to runtime page.
- Runtime auth pages render branding/template variants on login/signup (`auth-split`, `auth-minimal` fallback behavior).

## Last Run
- Command: `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Date: 2026-02-14 17:29 UTC
- Result: PASS (1 suite, 6 tests)
- Command: `cd frontend-reshet && npm test -- src/__tests__/published_apps --runInBand`
- Date: 2026-02-14 18:12 UTC
- Result: PASS (4 suites, 9 tests)
- Command: `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Date: 2026-02-14 20:42 UTC
- Result: PASS (1 suite, 8 tests)
- Command: `cd frontend-reshet && npm test -- src/__tests__/published_apps --runInBand`
- Date: 2026-02-15 20:34 UTC
- Result: PASS (5 suites, 17 tests)
- Command: `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Date: 2026-02-16 18:56 EET
- Result: PASS (1 suite, 13 tests)
- Command: `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Date: 2026-02-16 19:06 EET
- Result: PASS (1 suite, 14 tests)
- Command: `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Date: 2026-02-16 19:26 EET
- Result: PASS (1 suite, 14 tests)

## Known Gaps / Follow-ups
- Add tests for app detail publish/unpublish actions.
- Add tests for Google OAuth callback page token ingestion.
