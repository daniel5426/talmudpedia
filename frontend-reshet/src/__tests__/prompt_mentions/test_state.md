Last Updated: 2026-03-22

# Prompt Mentions Test State

## Scope
- Shared prompt token parsing/serialization.
- JSON-schema description scanning for prompt mentions.

## Test Files Present
- `prompt_mentions_utils.test.ts`
- `prompt_mention_json_utils.test.ts`

## Key Scenarios Covered
- Persisted `[[prompt:UUID]]` strings parse and serialize correctly.
- Filling one mention only replaces the targeted occurrence.
- JSON description ranges are identified without activating prompt logic on unrelated keys.
- Prompt tokens and `@query` detection work inside JSON `description` values.
- Raw prompt fill text is escaped correctly for JSON string content.

## Last Run
- Command: `pnpm test -- --runTestsByPath src/__tests__/prompt_mentions/prompt_mentions_utils.test.ts src/__tests__/prompt_mentions/prompt_mention_json_utils.test.ts --runInBand`
- Date: 2026-03-22
- Result: pass

## Known Gaps
- No component-level coverage yet for modal open/save/fill flows.
- No browser interaction coverage yet for CodeMirror decorations and click handling.
- Cross-page integration coverage is still manual for tools, pipelines, artifacts, and export dialog wiring.
