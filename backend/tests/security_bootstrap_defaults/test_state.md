# Security Bootstrap Defaults Test State

Last Updated: 2026-04-20

## Scope
Validate tenant bootstrap seeding for default roles and owner assignment.

## Test Files
- test_security_bootstrap_defaults.py

## Key Scenarios Covered
- Default system roles seeded (`Owner`, `Reader`, `Member`, `Viewer`)
- Owner assignment seeding is idempotent
- `app.core.security` fails closed when `SECRET_KEY` is missing or still set to placeholder defaults

## Last Run
- Command: `SECRET_KEY=explicit-test-secret-0123456789abcdef TEST_USE_REAL_DB=0 /Users/danielbenassaya/Code/personal/talmudpedia/backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/security_bootstrap_defaults/test_security_bootstrap_defaults.py`
- Date/Time: 2026-04-19 Asia/Hebron
- Result: PASS (`5 passed`)
- Command: `pytest -q backend/tests/security_scope_registry backend/tests/role_assignments_model backend/tests/security_bootstrap_defaults backend/tests/security_workload_provisioning backend/tests/security_route_enforcement backend/tests/security_admin_user_management`
- Date/Time: 2026-03-05
- Result: pass

## Known Gaps
- Does not verify seeding via every API entrypoint in one integration test.
