# Published Apps Frontend Tests

Last Updated: 2026-02-11

## Scope
Frontend coverage for:
- Admin Apps management page behavior.
- Builder workspace behavior (`Preview | Code`, template reset confirm, builder patch apply/save).
- Builder preview runtime behavior (build-status polling + preview runtime descriptor URL usage).
- Published runtime auth gating.
- Published login flow token persistence.
- Published runtime custom-UI compile/render behavior.
- Constant template chat streaming behavior.

## Test Files
- `frontend-reshet/src/__tests__/published_apps/apps_admin_page.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/apps_builder_workspace.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_runtime_gate.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_auth_flows.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_chat_template.test.tsx`

## Key Scenarios Covered
- Apps admin page loads existing apps and submits create payload.
- Apps admin create modal supports template selection and builder-route redirect on create.
- Builder workspace renders tabs, persists draft revision saves, confirms template overwrite, and applies streamed patch ops to revision save.
- Builder workspace fetches revision build status and loads preview iframe URL from preview runtime descriptor (`asset_base_url`) after successful builds.
- Runtime page redirects to login when app auth is enabled without token.
- Runtime page selects custom UI path when config indicates `has_custom_ui`, and falls back to chat template path otherwise.
- Login stores app-scoped bearer token and redirects to runtime page.
- Chat template submits input and renders streamed assistant token content.

## Last Run
- Command: `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx src/__tests__/published_apps/published_runtime_gate.test.tsx`
- Date: 2026-02-11 23:59 UTC
- Result: PASS (2 suites, 4 tests)

## Known Gaps / Follow-ups
- Add tests for app detail publish/unpublish actions.
- Add tests for Google OAuth callback page token ingestion.
- Add tests for deterministic Preview/Code tab switching assertions tied to virtual file explorer rendering.
