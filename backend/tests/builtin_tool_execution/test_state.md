# Built-in Tool Execution Tests

Last Updated: 2026-02-15

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
- `web_search` tenant credentials lookup via Settings (`category=custom`) when tool-local key is absent.
- `web_search` fallback to platform env key (`SERPER_API_KEY`) when tenant override is absent.
- `json_transform` and `datetime_utils` behavior contracts.

## Last run command + result
- Command: `pytest -q backend/tests/builtin_tool_execution/test_builtin_tool_executor.py`
- Date/Time: 2026-02-15 21:05 EET
- Result: pass (9 passed)

## Known gaps or follow-ups
- Add regression coverage for provider-specific malformed chunk payloads across SDK versions.
