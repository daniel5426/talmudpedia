# Workload Delegation Auth Tests

Last Updated: 2026-02-07

Scope of the feature:
- Delegated workload identity and token broker behavior for internal SaaS agent flows.
- Group A endpoint scope enforcement with workload tokens.
- Approval and revocation behavior for workload policies and grants.

Test files present:
- test_token_broker_jwt_claims.py
- test_scope_intersection_policy.py
- test_endpoint_scope_enforcement_group_a.py
- test_endpoint_scope_enforcement_group_bc.py
- test_phase2_runtime_propagation.py
- test_platform_sdk_delegated_auth_flow.py
- test_approval_workflow.py
- test_revocation_and_expiry.py

Key scenarios covered:
- JWT issuance claims and jti persistence.
- Effective scope intersection between user/workload/requested scopes.
- Group A endpoint rejects legacy token and accepts delegated scoped token.
- Group B/C endpoints reject legacy tokens and enforce scope checks.
- Sensitive mutation routes require explicit approval decisions for workload principals.
- Agent run records preserve delegated context from workload-initiated execution.
- Tool executor blocks workload-token mode without delegation grant.
- Platform SDK auth flow obtains delegated token through internal auth endpoints.
- Pending policy blocks workload token minting.
- Grant revocation invalidates token jti.

Last run command + date/time + result:
- `cd backend && pytest tests/workload_delegation_auth -q`
- 2026-02-08 00:14:56 EET
- PASS (12 passed)

Known gaps / follow-ups:
- Add direct integration coverage for `/internal/auth/*` and `/admin/security/workloads/*` API routes.
- Add expiry-time advancement test for `token_jti_registry` without grant revocation.
