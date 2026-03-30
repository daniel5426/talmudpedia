Last Updated: 2026-03-30

# Resource Policy Sets Frontend Test State

## Scope
Validate the resource policy sets frontend service contract and the admin page's core create, assignment, defaulting, loading, and error flows.

## Test Files
- resource_policy_sets_service.test.ts
- resource_policy_sets_page.test.tsx

## Key Scenarios Covered
- Service methods hit the exact backend routes for sets, includes, rules, assignments, and defaults
- Barrel exports keep the shared service under `frontend-reshet/src/services/`
- Admin page loading and empty states render correctly
- Create policy set flow works and surfaces backend conflict errors
- Assignment creation and default-policy mutations call the correct backend services
- The page restores the selected section from the URL query string on reload
- Detail modal rule editing updates quota rules through the existing patch endpoint

## Last Run
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/resource_policy_sets/resource_policy_sets_service.test.ts src/__tests__/resource_policy_sets/resource_policy_sets_page.test.tsx`
- Date/Time: 2026-03-30 Asia/Hebron
- Result: pass

## Known Gaps
- Detail-sheet include edit flows are not covered yet
- Delete flows and stale-object recovery are not covered yet
