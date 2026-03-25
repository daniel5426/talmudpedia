Last Updated: 2026-03-25

# Test State

## Scope

Artifact admin editor payload, dependency authoring, and form-state handling.

## Test Files Present

- `artifact_page_utils.test.ts`
- `artifact_dependency_tab.test.tsx`
- `artifact_list_view.test.tsx`
- `artifact_test_panel.test.tsx`
- `artifact_test_input.test.ts`

## Key Scenarios Covered

- build source-level credential mention tokens that carry immutable ids
- refresh visible credential labels from current Settings records
- include credential mention refs in artifact create/update payloads without artifact-side bindings
- hydrate editor form state from artifact responses without legacy binding fields
- warn on opposite-language code files at publish time while ignoring neutral files like `json` and `txt`
- render dependency analysis rows in the config dependency tab
- surface runtime-registry rows separately from broader Pyodide-catalog rows in the dependency tab
- verify Python dependencies before adding them through the dependency tab
- block duplicate declared dependencies in the dependency tab
- open the artifact editor when the list-row name is clicked
- route duplicate, publish, and delete through the artifact list actions menu
- generate schema-based default artifact test input payloads
- validate artifact test input payloads against contract input schema before run
- reject wrapped legacy tool-contract JSON in the admin editor save path
- stop unwrapping wrapped legacy tool-contract shapes when generating artifact test input schemas
- run artifact tests with the latest in-editor JSON even when edit and run happen in one interaction

## Last Run

- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_page_utils.test.ts`
- Date: 2026-03-24 Asia/Hebron
- Result: Pass (1 suite, 4 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_page_utils.test.ts src/__tests__/artifacts_admin/artifact_dependency_tab.test.tsx`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (2 suites, 7 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_list_view.test.tsx`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (1 suite, 2 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_page_utils.test.ts`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (1 suite, 5 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_test_input.test.ts src/__tests__/artifacts_admin/artifact_dependency_tab.test.tsx`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (2 suites, 6 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_test_input.test.ts`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (1 suite, 4 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_page_utils.test.ts src/__tests__/artifacts_admin/artifact_test_input.test.ts src/__tests__/artifacts_admin/artifact_test_panel.test.tsx`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (3 suites, 11 tests)

## Known Gaps

- no Monaco interaction coverage yet for the `@` credential mention dropdown
- no end-to-end frontend test yet for artifact save flows with source credential refs
- no browser-level coverage yet for the full config tab switch flow
- no browser-level coverage with the real Monaco editor; the artifact test panel regression uses a focused editor mock
