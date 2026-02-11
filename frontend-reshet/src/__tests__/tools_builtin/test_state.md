# Tools Built-in Frontend Tests

Last Updated: 2026-02-10

## Scope
Covers built-in templates UX, instance creation wiring, and tool bucket filtering behavior.

## Test files present
- tools_builtin_page.test.tsx
- tool_bucket_filtering.test.ts

## Key scenarios covered
- Built-in template browser renders data from `/tools/builtins/templates`.
- Retrieval built-in instance creation passes selected pipeline ID through payload wiring.
- Bucket/subtype filtering remains coherent with built-in metadata.

## Last run command + date/time + result
- Command: `npm test -- --runTestsByPath src/__tests__/tools_builtin/tools_builtin_page.test.tsx src/__tests__/tools_builtin/tool_bucket_filtering.test.ts`
- Date/Time: 2026-02-10 22:44 EET
- Result: pass (2 suites, 4 tests)

## Known gaps or follow-ups
- Add UI regression coverage for built-in instance publish action from the tools table.
