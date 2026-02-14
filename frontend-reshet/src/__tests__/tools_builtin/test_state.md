# Tools Built-in Frontend Tests

Last Updated: 2026-02-14

## Scope
Covers built-in templates UX, read-only catalog behavior, and regular tool creation wiring (`rag_retrieval` + `agent_call`).

## Test files present
- tools_builtin_page.test.tsx
- tool_bucket_filtering.test.ts

## Key scenarios covered
- Built-in template browser renders data from `/tools/builtins/templates`.
- Built-in instance creation action is removed from the tools page.
- Regular `rag_retrieval` tool creation passes selected pipeline ID through payload wiring.
- Regular `agent_call` tool creation maps target slug + timeout into the request payload.
- Bucket/subtype filtering remains coherent with built-in metadata.

## Last run command + date/time + result
- Command: `npm test -- --runTestsByPath src/__tests__/tools_builtin/tools_builtin_page.test.tsx src/__tests__/tools_builtin/tool_bucket_filtering.test.ts`
- Date/Time: 2026-02-14 20:47 EET
- Result: failed in local env before test execution (`@next/swc-darwin-x64` missing: "Failed to load bindings")

## Known gaps or follow-ups
- Re-run the suite once SWC binary/install issue is fixed in the frontend environment.
