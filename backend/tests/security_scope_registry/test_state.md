# Security Scope Registry Test State

Last Updated: 2026-03-05

## Scope
Validate canonical scope registry integrity and default role/profile coverage.

## Test Files
- test_scope_registry.py

## Key Scenarios Covered
- Action->scope requirements are represented in `ALL_SCOPES`
- Platform Architect profile includes model/knowledge-store write scopes
- Default tenant role bundles include expected admin/member boundaries
- Scope catalog shape includes groups and defaults

## Last Run
- Command: `pytest -q backend/tests/security_scope_registry backend/tests/security_rbac_scope_model backend/tests/security_bootstrap_defaults backend/tests/security_workload_provisioning backend/tests/security_route_enforcement backend/tests/security_admin_user_management`
- Date/Time: 2026-03-05
- Result: pass

## Known Gaps
- Does not validate runtime enforcement against endpoint dependencies.
