# Tools Built-in Frontend Tests

Last Updated: 2026-03-15

## Scope
Covers built-in tools UX under the single-list architecture, plus bucket/subtype classification behavior.

## Test files present
- tools_builtin_page.test.tsx
- tool_bucket_filtering.test.ts

## Key scenarios covered
- Built-in tools are rendered from the main `/tools` list (no template browser dependency).
- Built-in instance creation action is removed from the tools page.
- Bucket/subtype filtering remains coherent with built-in metadata.
- Artifact-backed and pipeline-backed rows now expose redirect/open-editor actions instead of registry-side editing or publish flows.

## Last run command + date/time + result
- Command: `npm test -- --runInBand src/__tests__/tools_builtin/tools_builtin_page.test.tsx`
- Date/Time: 2026-03-15 (Asia/Hebron local)
- Result: pass (`1 suite, 4 passed`)
- Command: `npm test -- --runInBand src/__tests__/tools_builtin/tool_bucket_filtering.test.ts src/__tests__/tools_builtin/tools_builtin_page.test.tsx`
- Date/Time: 2026-03-11 (Asia/Hebron local)
- Result: pass (`2 suites, 4 passed, 2 skipped`)
- Command: `npm test -- --runInBand src/__tests__/tools_builtin/tool_bucket_filtering.test.ts`
- Date/Time: 2026-02-15 (local)
- Result: pass (`1 suite, 2 tests`)
- Command: `npm test -- --runInBand src/__tests__/tools_builtin/tools_builtin_page.test.tsx`
- Date/Time: 2026-02-15 (local)
- Result: pass (`1 suite, 2 passed, 2 skipped`)

## Known gaps or follow-ups
- Add dedicated coverage for the pipeline page tool settings panel (`Use as tool`, schema editing, compile refresh).
