Last Updated: 2026-04-21

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
- Organization-owned prompt create/list/read flows are scoped to the active project while global prompts remain cross-project

## Last Run

- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/prompt_library/test_prompt_library_api.py::test_prompt_library_crud_and_resolve_preview backend/tests/prompt_library/test_prompt_library_api.py::test_prompt_delete_is_blocked_when_agent_references_it backend/tests/prompt_library/test_prompt_library_api.py::test_paused_run_status_includes_resolved_interaction_prompt`
- Date: 2026-04-21 Asia/Hebron
- Result: PASS (`3 passed`)
- Command: `cd backend && pytest tests/prompt_library/test_prompt_library_api.py`
- Date: 2026-03-19 18:42:01 EET
- Result: Pass
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia backend/.venv/bin/python -m pytest -q backend/tests/prompt_library/test_prompt_library_api.py -x`
- Date: 2026-04-21 Asia/Hebron
- Result: fail on first create-route assertion. Local prompt writes currently error with `invalid input value for enum promptscope: "organization"` before prompt-library assertions run.

## Known Gaps

- No direct API test yet for rollback/archive/restore flows
- No end-to-end execution test yet for prompt resolution inside full agent runs
- No direct route test yet for tool/artifact authoring validation failures
- The full directory still has unrelated local enum drift outside the validated slice (`ArtifactOwnerType` vs DB enum values) when usage-scanner coverage reaches artifact-owned prompt paths.
