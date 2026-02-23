# Built-in Tool Execution Tests

Last Updated: 2026-02-22

## Scope
Covers runtime behavior of Built-in Tools v1 dispatch and mode-based execution guardrails.

## Test files present
- test_builtin_tool_executor.py

## Key scenarios covered
- `retrieval_pipeline` dispatch executes the retrieval runtime path.
- `retrieval_pipeline` accepts query passed as scalar `input` payload.
- Unknown implementation types return explicit execution errors.
- Production mode blocks draft tools while debug mode allows execution.
- `web_fetch` happy/error paths.
- `web_search` provider dispatch wiring for `serper`, `tavily`, and `exa`.
- `web_search` tenant credentials lookup via default Integration Credentials (`category=tool_provider`) when tool-local key is absent.
- `web_search` fallback to provider env keys (`SERPER_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY`) when no credential override is present.
- `json_transform` and `datetime_utils` behavior contracts.

## Last run command + result
- Command: `PYTHONPATH=. pytest -q tests/builtin_tool_execution`
- Date/Time: 2026-02-22
- Result: pass (14 passed)

## Known gaps or follow-ups
- Add regression coverage for provider-specific malformed chunk payloads across SDK versions.
