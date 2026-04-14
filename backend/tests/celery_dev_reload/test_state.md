# Test State: Celery Dev Reload

Last Updated: 2026-04-14

**Scope**
Local Celery dev-reload supervision helpers and process-detection contracts.

**Test Files**
- `test_dev_reload.py`

**Scenarios Covered**
- `run_celery.py` command building includes `--reload` only when explicitly enabled
- worker detection patterns cover both supervisor and direct Celery worker processes
- watched Python file changes produce a different snapshot
- missing watch paths are ignored deterministically

**Last Run**
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/celery_dev_reload/test_dev_reload.py`
- Date: 2026-04-14 17:19:49 EEST
- Result: PASS (`4 passed, 1 warning`)

**Known Gaps / Follow-ups**
- No subprocess-level integration test yet for full worker restart behavior
- No coverage yet for signal-forwarding during in-flight task shutdown
