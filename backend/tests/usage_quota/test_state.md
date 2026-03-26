# Test State: Usage Quota

Last Updated: 2026-03-26

**Scope**
Usage quota reserve/settle/release/reconcile behavior for tenant and user scopes.

**Test Files**
- `test_usage_quota_service.py`

**Scenarios Covered**
- Reserve success when both scopes are under limits
- User-scope rejection when over limit
- Tenant-scope rejection when over limit
- Settle idempotency and reserved-to-used accounting
- Release and stale-expire reservation flows
- Reconciliation from persisted run accounting totals with `usage_tokens` as a legacy mirror

**Last Run**
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/usage_quota/test_usage_quota_service.py`
- Date/Time: 2026-03-26 Asia/Hebron
- Result: PASS (`6 passed`)

**Known Gaps / Follow-ups**
- Concurrency race tests with real PostgreSQL row-level locks are not included in this suite
- Endpoint-level quota 429 payload assertions are still covered indirectly by stream/API suites
