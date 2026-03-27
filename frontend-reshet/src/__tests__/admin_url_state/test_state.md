Last Updated: 2026-03-27

# Test State

## Scope

Shared admin-page URL query state helpers that persist selected tabs and sections across reloads.

## Test Files Present

- `url_query_state.test.ts`

## Key Scenarios Covered

- coerce invalid query-string enum values back to a safe fallback
- update a query-backed UI state key while preserving unrelated params
- remove the state key from the URL when the fallback value is selected

## Last Run

- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_routes.test.ts src/__tests__/admin_url_state/url_query_state.test.ts src/__tests__/resource_policy_sets/resource_policy_sets_page.test.tsx`
- Date: 2026-03-27 Asia/Hebron
- Result: Pass (3 suites, 9 tests)

## Known Gaps

- no hook-level render test yet for `useUrlEnumState`
- no direct page-level coverage yet for the security tab restoration flow
