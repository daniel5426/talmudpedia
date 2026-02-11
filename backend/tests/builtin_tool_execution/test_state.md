# Built-in Tool Execution Tests

Last Updated: 2026-02-11

## Scope
Covers runtime behavior of Built-in Tools v1 dispatch and mode-based execution guardrails.

## Test files present
- test_builtin_tool_executor.py

## Key scenarios covered
- `retrieval_pipeline` dispatch executes the retrieval runtime path.
- Unknown implementation types return explicit execution errors.
- Production mode blocks draft tools while debug mode allows execution.
- `web_fetch` happy/error paths.
- `web_search` provider dispatch wiring.
- `json_transform` and `datetime_utils` behavior contracts.

## Last run command + result
- Command: `pytest -q backend/tests/agent_tool_usecases backend/tests/agent_tool_loop backend/tests/builtin_tool_execution`
- Date/Time: 2026-02-11 16:07 EET
- Result: pass (15 passed)

## Known gaps or follow-ups
- Add integration coverage for real credentials lookup (`credentials_ref`) on `web_search`.
- Add regression coverage for provider-specific malformed chunk payloads across SDK versions.
