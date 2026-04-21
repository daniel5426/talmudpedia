# Auth Session Bootstrap Tests

Last Updated: 2026-04-21

## Scope
Frontend coverage for mount-time browser session bootstrap, specifically stalled `/auth/session` requests and duplicate session refresh calls.

## Test Files
- `frontend-reshet/src/__tests__/auth_session_bootstrap/auth_service.test.ts`
- `frontend-reshet/src/__tests__/auth_session_bootstrap/auth_refresher.test.tsx`
- `frontend-reshet/src/__tests__/auth_session_bootstrap/http_client_auth_handling.test.ts`
- `frontend-reshet/src/__tests__/auth_session_bootstrap/admin_layout_auth_gate.test.tsx`

## Key Scenarios Covered
- Concurrent `authService.getCurrentSession()` callers share a single in-flight `/auth/session` request.
- Stalled `/auth/session` requests time out instead of hanging forever.
- Frontend permission gating treats backend `effective_scopes` as canonical and does not translate legacy permission names.
- `AuthRefresher` preserves the current auth snapshot and flips `sessionChecked` after a session-bootstrap timeout.
- Generic non-session `401` responses no longer force a global logout.
- Authenticated users with an established browser session are not bounced from `/admin` back to landing merely because `effective_scopes` is empty.

## Last Run
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/auth_session_bootstrap/auth_service.test.ts`
- Date: 2026-04-20 Asia/Hebron
- Result: PASS (`1 suite, 3 tests`)

## Known Gaps / Follow-ups
- No browser-level integration test yet for `/admin` redirect behavior after a timed-out bootstrap.

## 2026-04-21 validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/auth_session_bootstrap/auth_service.test.ts`
- Result: `1 suite passed`

## 2026-04-21 tenant-to-organization validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/admin_threads/threads_table.test.ts src/__tests__/admin_threads/admin_thread_page.test.tsx src/__tests__/admin_monitoring/users_table_monitoring.test.tsx src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx src/__tests__/artifacts_admin/artifact_test_panel.test.tsx src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx src/__tests__/agent_builder_v3/config_panel_value_ref_contracts.test.tsx src/__tests__/agent_builder_v3/config_panel_artifact_contracts.test.tsx src/__tests__/pipeline_tool_bindings/pipeline_tool_settings_page.test.tsx`
- Result: PASS (`11 suites passed, 25 tests passed`)
