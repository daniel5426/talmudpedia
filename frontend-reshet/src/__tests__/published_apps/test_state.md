# Published Apps Frontend Tests

Last Updated: 2026-02-11

## Scope
Frontend coverage for:
- Admin Apps management page behavior.
- Builder workspace behavior (`Preview | Code`, template reset confirm, builder patch apply/save).
- Builder preview runtime behavior (build-status polling + preview runtime descriptor URL usage).
- Published runtime redirect behavior.
- Published login flow token persistence.
- Published runtime error handling when runtime descriptor cannot be resolved.

## Test Files
- `frontend-reshet/src/__tests__/published_apps/apps_admin_page.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/apps_builder_workspace.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_runtime_gate.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_auth_flows.test.tsx`

## Key Scenarios Covered
- Apps admin page loads existing apps and submits create payload.
- Apps admin create modal supports template selection and builder-route redirect on create.
- Builder workspace renders tabs, persists draft revision saves, confirms template overwrite, and applies streamed patch ops to revision save.
- Builder workspace fetches revision build status and loads preview iframe URL from preview runtime descriptor (`asset_base_url`) after successful builds.
- Runtime page redirects directly to static published runtime URL via `/public/apps/{slug}/runtime`.
- Login stores app-scoped bearer token and redirects to runtime page.

## Last Run
- Command: `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx src/__tests__/published_apps/published_runtime_gate.test.tsx src/__tests__/published_apps/published_auth_flows.test.tsx --runInBand`
- Date: 2026-02-11 23:59 UTC
- Result: PASS (3 suites, 5 tests)

## Known Gaps / Follow-ups
- Add tests for app detail publish/unpublish actions.
- Add tests for Google OAuth callback page token ingestion.
- Add tests for deterministic Preview/Code tab switching assertions tied to virtual file explorer rendering.
