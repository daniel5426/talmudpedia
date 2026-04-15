Last Updated: 2026-04-15

# Platform Native Adapter Test State

## Scope
Thin native control-plane adapter behavior and contract guards.

## Test Files
- `test_platform_native_adapter.py`

## Scenarios Covered
- Runtime context stays separate from payload and reaches handlers
- Debug trace metadata does not leak into tool outputs
- Removed alias actions fail instead of being normalized
- Native `platform-rag` `rag.create_job` schedules background job dispatch after creating the pipeline job row

## Last Run
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_native_adapter/test_platform_native_adapter.py`
- Date: 2026-04-15 03:16 EEST
- Result: passed (`3 passed, 7 warnings`)

## Known Gaps
- No full cross-domain integration coverage yet
