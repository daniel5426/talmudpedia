Last Updated: 2026-03-24

# Test State

## Scope

Artifact admin editor payload and form-state handling.

## Test Files Present

- `artifact_page_utils.test.ts`

## Key Scenarios Covered

- build source-level credential mention tokens that carry immutable ids
- refresh visible credential labels from current Settings records
- include credential mention refs in artifact create/update payloads without artifact-side bindings
- hydrate editor form state from artifact responses without legacy binding fields

## Last Run

- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_page_utils.test.ts`
- Date: 2026-03-24 Asia/Hebron
- Result: Pass (1 suite, 4 tests)

## Known Gaps

- no Monaco interaction coverage yet for the `@` credential mention dropdown
- no end-to-end frontend test yet for artifact save flows with source credential refs
