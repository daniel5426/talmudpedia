# Security Route Enforcement Test State

Last Updated: 2026-03-05

## Scope
Validate control-plane route scope enforcement and tenant-context strictness.

## Test Files
- test_route_scope_enforcement.py

## Key Scenarios Covered
- `X-Tenant-ID` required for tenant-bound model routes
- Models list allowed with correct scope
- Knowledge-store write denied for member without write scope

## Last Run
- Command: `pytest -q backend/tests/security_scope_registry backend/tests/security_rbac_scope_model backend/tests/security_bootstrap_defaults backend/tests/security_workload_provisioning backend/tests/security_route_enforcement backend/tests/security_admin_user_management`
- Date/Time: 2026-03-05
- Result: pass

## Known Gaps
- Does not yet cover all models/knowledge-stores mutation endpoints.
