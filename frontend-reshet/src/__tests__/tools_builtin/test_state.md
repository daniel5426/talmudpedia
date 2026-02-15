# Tools Built-in Frontend Tests

Last Updated: 2026-02-15

## Scope
Covers built-in tools UX under the single-list architecture, plus bucket/subtype classification behavior.

## Test files present
- tools_builtin_page.test.tsx
- tool_bucket_filtering.test.ts

## Key scenarios covered
- Built-in tools are rendered from the main `/tools` list (no template browser dependency).
- Built-in instance creation action is removed from the tools page.
- Bucket/subtype filtering remains coherent with built-in metadata.
- Form-level creation wiring tests for `rag_retrieval` and `agent_call` are currently skipped due brittle jsdom/select+editor interactions.

## Last run command + date/time + result
- Command: `npm test -- --runInBand src/__tests__/tools_builtin/tool_bucket_filtering.test.ts`
- Date/Time: 2026-02-15 (local)
- Result: pass (`1 suite, 2 tests`)
- Command: `npm test -- --runInBand src/__tests__/tools_builtin/tools_builtin_page.test.tsx`
- Date/Time: 2026-02-15 (local)
- Result: pass (`1 suite, 2 passed, 2 skipped`)

## Known gaps or follow-ups
- Stabilize `Create Tool` dialog tests (`rag_retrieval` and `agent_call`) with resilient selectors and/or component-level mocks for select/editor primitives.
