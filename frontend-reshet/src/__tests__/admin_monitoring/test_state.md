# Admin Monitoring Test State

Last Updated: 2026-03-19

## Scope
Validate frontend monitoring service filters and unified monitored-users table behavior.

## Test Files
- admin_service_monitoring_filters.test.ts
- users_table_monitoring.test.tsx

## Key Scenarios Covered
- Admin service sends actor, agent, surface, and agent-stats scope params
- Users table renders mixed monitored actor types
- External actors are shown as read-only in the unified Users table

## Last Run
- Command: `cd frontend-reshet && pnpm test -- --runInBand src/__tests__/admin_monitoring`
- Date/Time: 2026-03-19 03:05:07 EET
- Result: pass (2 suites, 4 tests)

## Known Gaps
- Does not yet cover thread detail rendering or stats tab agent selector interactions.
