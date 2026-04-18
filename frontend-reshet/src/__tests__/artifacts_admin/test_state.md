Last Updated: 2026-04-16

# Test State

## Scope

Artifact admin editor payload, dependency authoring, and form-state handling.

## Test Files Present

- `artifact_page_utils.test.ts`
- `artifact_routes.test.ts`
- `artifact_dependency_tab.test.tsx`
- `artifact_list_view.test.tsx`
- `artifact_test_panel.test.tsx`
- `artifact_test_input.test.ts`
- `artifact_workspace_editor.test.tsx`

## Key Scenarios Covered

- build source-level credential mention tokens that carry immutable ids
- refresh visible credential labels from current Settings records
- include credential mention refs in artifact create/update payloads without artifact-side bindings
- propagate the artifact coding `draft_key` through artifact save payloads so saved artifacts can relink coding history
- hydrate editor form state from artifact responses without legacy binding fields
- build dedicated artifact detail/create routes without falling back to query-mode editor routing
- warn on opposite-language code files at publish time while ignoring neutral files like `json` and `txt`
- render dependency analysis rows in the config dependency tab
- surface runtime-registry rows separately from broader Pyodide-catalog rows in the dependency tab
- verify Python dependencies before adding them through the dependency tab
- block duplicate declared dependencies in the dependency tab
- open the artifact editor when the list-row name is clicked
- route duplicate, publish, and delete through the artifact list actions menu
- route artifact file download through the artifact list actions menu
- pass selected artifact transfer files through the upload control
- generate schema-based default artifact test input payloads
- validate artifact test input payloads against contract input schema before run
- reject wrapped legacy tool-contract JSON in the admin editor save path
- stop unwrapping wrapped legacy tool-contract shapes when generating artifact test input schemas
- run artifact tests with the latest in-editor JSON even when edit and run happen in one interaction
- treat semantically equivalent JSON/dependency formatting as clean after save so the unsaved indicator clears
- round-trip copied artifact configuration payloads across artifact editors of the same kind/language
- reject copied configuration payloads when the kind or entry module path does not match the current artifact
- open the artifact file-tree action menu on double click
- download a single source file from the artifact file-tree action menu
- keep the artifact file-tree action menu closed on single click

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
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_page_utils.test.ts`
- Date: 2026-03-26 01:19:41 EET
- Result: Pass (1 suite, 7 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_page_utils.test.ts`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`1 suite, 8 tests`)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_routes.test.ts src/__tests__/admin_url_state/url_query_state.test.ts src/__tests__/resource_policy_sets/resource_policy_sets_page.test.tsx`
- Date: 2026-03-27 Asia/Hebron
- Result: Pass (3 suites, 9 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_list_view.test.tsx`
- Date: 2026-04-16 Asia/Hebron
- Result: Pass (1 suite, 4 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifacts_admin/artifact_workspace_editor.test.tsx`
- Date: 2026-04-16 20:58:33 EEST
- Result: Pass (1 suite, 2 tests)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/files_domain/file_space_workspace_editor.test.tsx src/__tests__/artifacts_admin/artifact_workspace_editor.test.tsx`
- Date: 2026-04-17 15:20:33 EEST
- Result: Pass (2 suites, 6 tests)

## Known Gaps

- no Monaco interaction coverage yet for the `@` credential mention dropdown
- no end-to-end frontend test yet for artifact save flows with source credential refs
- no browser-level coverage yet for the full config tab switch flow
- no browser-level coverage with the real Monaco editor; the artifact test panel regression uses a focused editor mock
- no browser-level coverage yet for the config-tab clipboard shortcuts
- no browser-level coverage yet for the artifact tree action menu
