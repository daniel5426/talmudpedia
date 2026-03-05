# Security Workload Provisioning Test State

Last Updated: 2026-03-05

## Scope
Validate provisioning-time workload principal/policy behavior and strict runtime failures.

## Test Files
- test_workload_provisioning.py

## Key Scenarios Covered
- Admin actor provisioning auto-approves policy
- Non-admin provisioning remains pending
- Runtime grant creation fails when agent principal is not provisioned

## Last Run
- Command: `pytest -q backend/tests/security_scope_registry backend/tests/security_rbac_scope_model backend/tests/security_bootstrap_defaults backend/tests/security_workload_provisioning backend/tests/security_route_enforcement backend/tests/security_admin_user_management`
- Date/Time: 2026-03-05
- Result: pass

## Known Gaps
- Does not yet assert policy version bump on scope-change updates.
