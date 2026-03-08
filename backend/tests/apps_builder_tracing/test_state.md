Last Updated: 2026-03-08

## Scope
- Shared app-builder lifecycle tracing across draft-dev runtime, E2B sandbox lifecycle, coding-agent pipeline bridge, preview proxy, and publish/build flows.

## Test Files
- `backend/tests/apps_builder_tracing/test_apps_builder_trace.py`

## Key Scenarios Covered
- Shared `apps_builder_trace` writes structured JSONL events when enabled.
- Existing coding-agent `pipeline_trace` events are mirrored into the shared app-builder trace stream.

## Last Run
- Command: `cd backend && PYTHONPATH=. pytest -q tests/apps_builder_tracing/test_apps_builder_trace.py`
- Date/Time: 2026-03-08
- Result: Pass (2 passed, 1 warning)

## Known Gaps / Follow-ups
- Runtime integration coverage for trace emission in live E2B sessions is still manual.
- Future follow-up: add API or admin surface to read shared app-builder trace events without tailing the JSONL file directly.
