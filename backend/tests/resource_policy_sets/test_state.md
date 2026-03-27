# Resource Policy Sets Test State

Last Updated: 2026-03-27

## Scope
Validate the resource policy set domain across service resolution, admin API, runtime enforcement, quota accounting, and real-DB migration coverage.

## Test Files
- test_policy_set_model_and_resolution.py
- test_policy_set_admin_api.py
- test_policy_set_runtime_enforcement.py
- test_policy_set_quota_accounting.py
- test_policy_set_migration_real_db.py

## Key Scenarios Covered
- Direct assignment, published-app default, embedded default, nested includes, inactive sets, and snapshot round-trips resolve as expected
- Admin CRUD, include/rule/assignment/default routes enforce scopes, conflict behavior, and cross-tenant reference validation
- Admin-facing app and agent list responses expose persisted default policy IDs for Defaults-tab reloads
- Runtime agent start, tool/model/knowledge-store boundaries, malformed top-level snapshots, and nested child-run snapshot propagation are covered
- Model quota reservation and settlement follow canonical persisted accounting semantics and explicit monthly counter behavior
- Real Postgres migration coverage locks schema objects, indexes, enum lifecycle, downgrade cleanup, and rerun safety

## Last Run
- Command: `pytest backend/tests/resource_policy_sets -q -k 'not real_db'`
- Date/Time: 2026-03-26 23:01:01 EET
- Result: pass
- Command: `TEST_USE_REAL_DB=1 pytest backend/tests/resource_policy_sets/test_policy_set_migration_real_db.py -q`
- Date/Time: 2026-03-26 23:01:01 EET
- Result: pass

## Known Gaps
- Live provider-backed runtime/quota executions are still not covered in this feature folder
- Frontend delete/detail mutation paths are covered in the frontend feature folder, not here
