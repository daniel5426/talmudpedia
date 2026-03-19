# Tools Built-in Frontend Tests

Last Updated: 2026-03-19

## Scope
Covers built-in tools UX under the single-list architecture, plus bucket/subtype classification behavior.

## Test files present
- tools_builtin_page.test.tsx
- tool_bucket_filtering.test.ts

## Key scenarios covered
- Built-in tools are rendered from the main `/tools` list (no template browser dependency).
- Built-in instance creation action is removed from the tools page.
- The top-level create flow now routes by owning surface instead of assuming `/tools` authors every tool type.
- Manual tool creation still opens the registry-native create dialog.
- Artifact tool creation routes to artifact-native `tool_impl` create mode.
- Pipeline tool creation routes to the pipeline authoring surface.
- Agent/workflow tool creation now routes to the agents export flow.
- Bucket/subtype filtering remains coherent with built-in metadata.
- Artifact-backed, pipeline-backed, and agent-backed rows now expose redirect/open-editor actions instead of registry-side editing or publish flows.
- The tools detail sheet consumes canonical DTO fields (`implementation_config`, `execution_config`) instead of reconstructing from `config_schema`.
- The tools detail sheet now shows ownership/management metadata from the backend DTO.

## Last run command + date/time + result
- Command: `npm test -- --runInBand src/__tests__/tools_builtin/tool_bucket_filtering.test.ts src/__tests__/tools_builtin/tools_builtin_page.test.tsx`
- Date/Time: 2026-03-18 (Asia/Hebron local)
- Result: pass (`2 suites, 11 passed`)
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
- Add a focused tools-page test for the agent-bound "Open Editor" route.
