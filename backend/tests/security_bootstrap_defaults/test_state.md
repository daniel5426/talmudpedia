# Security Bootstrap Defaults Test State

Last Updated: 2026-03-05

## Scope
Validate tenant bootstrap seeding for default roles and owner assignment.

## Test Files
- test_security_bootstrap_defaults.py

## Key Scenarios Covered
- Default system roles seeded (`owner`, `admin`, `member`)
- Owner assignment seeding is idempotent

## Last Run
- Command: `pytest -q backend/tests/security_scope_registry backend/tests/security_rbac_scope_model backend/tests/security_bootstrap_defaults backend/tests/security_workload_provisioning backend/tests/security_route_enforcement backend/tests/security_admin_user_management`
- Date/Time: 2026-03-05
- Result: pass

## Known Gaps
- Does not verify seeding via every API entrypoint in one integration test.
