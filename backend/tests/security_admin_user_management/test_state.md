# Security Admin User Management Test State

Last Updated: 2026-04-21

## Scope
Validate admin user APIs enforce scopes and role edits are removed from update flow.

## Test Files
- test_admin_user_management.py

## Key Scenarios Covered
- Admin-scoped user can patch profile fields
- `role` payload is ignored by user update endpoint
- `users.read` scope required for `/admin/users`
- Auth helpers mint explicit scope claims instead of legacy `org_role` claims

## Last Run
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/security_bootstrap_defaults backend/tests/security_admin_user_management backend/tests/organization_bootstrap backend/tests/admin_stats_accounting backend/tests/role_assignments_model`
- Date/Time: 2026-04-21 21:13 EEST
- Result: PASS (`18 passed`)
- Command: `pytest -q backend/tests/security_scope_registry backend/tests/role_assignments_model backend/tests/security_bootstrap_defaults backend/tests/security_workload_provisioning backend/tests/security_route_enforcement backend/tests/security_admin_user_management`
- Date/Time: 2026-03-05
- Result: pass

## Known Gaps
- Does not test threads/stats admin endpoints yet.
