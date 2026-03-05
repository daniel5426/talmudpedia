# Security RBAC Scope Model Test State

Last Updated: 2026-03-05

## Scope
Validate scope-key RBAC persistence and permission resolution behavior.

## Test Files
- test_rbac_scope_model.py

## Key Scenarios Covered
- `check_permission` resolves through scope-key role permissions
- RolePermission persistence uses `scope_key`

## Last Run
- Command: `pytest -q backend/tests/security_scope_registry backend/tests/security_rbac_scope_model backend/tests/security_bootstrap_defaults backend/tests/security_workload_provisioning backend/tests/security_route_enforcement backend/tests/security_admin_user_management`
- Date/Time: 2026-03-05
- Result: pass

## Known Gaps
- No migration-level uniqueness conflict test yet.
