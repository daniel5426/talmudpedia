# Role Assignments Model Test State

Last Updated: 2026-04-21

## Scope
Validate explicit organization/project role-assignment persistence and local effective-scope resolution.

## Test Files
- test_role_assignments_model.py

## Key Scenarios Covered
- Local role assignments resolve canonical effective scopes
- Project role assignments persist through explicit `project_id`
- Membership fixtures no longer rely on the removed legacy org-membership role enum

## Last Run
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/security_bootstrap_defaults backend/tests/security_admin_user_management backend/tests/organization_bootstrap backend/tests/admin_stats_accounting backend/tests/role_assignments_model`
- Date/Time: 2026-04-21 21:13 EEST
- Result: PASS (`18 passed`)

## Known Gaps
- No migration-level invalid legacy-row coverage yet.
- No DB uniqueness assertion for the new partial unique indexes yet.
