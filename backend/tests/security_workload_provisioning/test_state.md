# Security Workload Provisioning Test State

Last Updated: 2026-03-09

## Scope
Validate provisioning-time workload principal/policy behavior and strict runtime failures.

## Test Files
- test_workload_provisioning.py

## Key Scenarios Covered
- Admin actor provisioning auto-approves policy
- Non-admin provisioning remains pending
- Runtime grant creation fails when agent principal is not provisioned
- Internal published-app coding-agent profile creation provisions a bound agent principal and approved policy so live coding runs can start

## Last Run
- Command: `pytest -q backend/tests/security_scope_registry backend/tests/security_rbac_scope_model backend/tests/security_bootstrap_defaults backend/tests/security_workload_provisioning backend/tests/security_route_enforcement backend/tests/security_admin_user_management`
- Date/Time: 2026-03-05
- Result: pass
- Command: `pytest -q backend/tests/security_workload_provisioning/test_workload_provisioning.py backend/tests/apps_builder_sandbox_runtime/test_live_coding_run_e2e.py`
- Date/Time: 2026-03-09 19:50 EET
- Result: pending local rerun after coding-agent profile provisioning fix

## Known Gaps
- Does not yet assert policy version bump on scope-change updates.
