# Built-in Tool Execution Tests

Last Updated: 2026-03-29

## Scope
Covers runtime behavior of Built-in Tools v1 dispatch and mode-based execution guardrails.

## Test files present
- test_builtin_tool_executor.py

## Key scenarios covered
- `retrieval_pipeline` authored rows now standardize on `rag_pipeline` metadata while built-in dispatch still exercises the retrieval runtime path.
- `retrieval_pipeline` accepts query passed as scalar `input` payload.
- Unknown implementation types return explicit execution errors.
- Production mode blocks draft tools while debug mode allows execution.
- `web_fetch` happy/error paths.
- `web_search` provider dispatch wiring for `serper`, `tavily`, and `exa`.
- `web_search` tenant credentials lookup via default Integration Credentials (`category=tool_provider`) when tool-local key is absent.
- `web_search` fallback to provider env keys (`SERPER_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY`) when no credential override is present.
- `json_transform` and `datetime_utils` behavior contracts.
- Legacy widget built-ins are absent from the built-in registry after the OpenUI hard cut.
- `ui_blocks` built-in validates starter-block bundles and returns canonical `ui_blocks_bundle` output.

## Last run command + result
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia/backend python3 -m pytest -q /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/builtin_tool_execution/test_builtin_tool_executor.py`
- Date/Time: 2026-03-19 15:18 Asia/Hebron
- Result: pass (15 passed)

## Known gaps or follow-ups
- Add regression coverage for provider-specific malformed chunk payloads across SDK versions.
