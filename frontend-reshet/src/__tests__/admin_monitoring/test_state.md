# Admin Monitoring Test State

Last Updated: 2026-04-21

## Scope
Validate frontend monitoring service filters and the monitoring-only Admin Users table behavior.

## Test Files
- admin_service_monitoring_filters.test.ts
- admin_service_user_update.test.ts
- users_table_monitoring.test.tsx

## Key Scenarios Covered
- Admin service sends actor, agent, surface, and agent-stats scope params
- Users table renders mixed monitored actor types
- External actors are shown as read-only in the unified Users table
- Admin Users no longer exposes legacy role-management controls

## Last Run
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/admin_monitoring/users_table_monitoring.test.tsx`
- Date/Time: 2026-04-20 Asia/Hebron
- Result: pass (1 suite, 1 test)

## Known Gaps
- Does not yet cover thread detail rendering or stats tab agent selector interactions.

## 2026-04-21 validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/admin_monitoring/users_table_monitoring.test.tsx`
- Result: `1 suite passed`

## 2026-04-21 tenant-to-organization validation
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/admin_monitoring/users_table_monitoring.test.tsx src/__tests__/admin_threads/threads_table.test.ts src/__tests__/admin_threads/admin_thread_page.test.tsx src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/settings_api_keys/settings_api_keys_service.test.ts src/__tests__/published_apps/preview_canvas_auth_channel.test.tsx`
- Result: PASS (`6 suites passed, 23 tests passed`)
