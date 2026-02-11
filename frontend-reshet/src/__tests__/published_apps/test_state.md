# Published Apps Frontend Tests

Last Updated: 2026-02-10

## Scope
Frontend coverage for:
- Admin Apps management page behavior.
- Published runtime auth gating.
- Published login flow token persistence.
- Constant template chat streaming behavior.

## Test Files
- `frontend-reshet/src/__tests__/published_apps/apps_admin_page.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_runtime_gate.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_auth_flows.test.tsx`
- `frontend-reshet/src/__tests__/published_apps/published_chat_template.test.tsx`

## Key Scenarios Covered
- Apps admin page loads existing apps and submits create payload.
- Runtime page redirects to login when app auth is enabled without token.
- Login stores app-scoped bearer token and redirects to runtime page.
- Chat template submits input and renders streamed assistant token content.

## Last Run
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps`
- Date: 2026-02-10 14:39 UTC
- Result: PASS (4 suites, 4 tests)

## Known Gaps / Follow-ups
- Add tests for app detail publish/unpublish actions.
- Add tests for Google OAuth callback page token ingestion.
- Add tests for chat history panel load/select states.
