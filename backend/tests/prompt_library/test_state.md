Last Updated: 2026-03-19

# Prompt Library Test State

## Scope

Backend coverage for the prompt library control-plane domain, prompt token resolution, paused interaction payloads, and usage scanning across agents, tools, and artifact tool contracts.

## Test Files Present

- `test_prompt_library_api.py`

## Key Scenarios Covered

- Prompt CRUD basics, mention search, nested resolve-preview, and rename/version behavior
- Delete blocked when an agent graph still references a prompt
- Paused run status returns resolved interaction payloads for `user_approval`
- Usage scanner detects prompt references in tool descriptions, tool schema descriptions, and artifact tool-contract schema descriptions

## Last Run

- Command: `cd backend && pytest tests/prompt_library/test_prompt_library_api.py`
- Date: 2026-03-19 18:42:01 EET
- Result: Pass

## Known Gaps

- No direct API test yet for rollback/archive/restore flows
- No end-to-end execution test yet for prompt resolution inside full agent runs
- No direct route test yet for tool/artifact authoring validation failures
