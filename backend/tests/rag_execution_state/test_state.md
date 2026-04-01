# RAG Execution State Test State

Last Updated: 2026-04-01

## Scope
- Freshness checks between visual pipeline drafts and executable pipeline artifacts.

## Test files present
- `test_stale_executable_state.py`

## Key scenarios covered
- A newer visual draft marks the executable as stale.
- Stale executables raise a structured compile-required error.
- Fresh executables remain runnable.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/rag_execution_state/test_stale_executable_state.py`
- Date/Time: 2026-04-01
- Result: pass (`3 passed`)

## Known gaps or follow-ups
- Add an API-level `/admin/pipelines/jobs` test for the stale executable `409` response.
