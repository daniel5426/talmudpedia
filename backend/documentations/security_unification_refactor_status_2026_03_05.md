# Security Unification Refactor Status

Last Updated: 2026-03-05

## Implemented in This Wave
- Added canonical scope registry at `backend/app/core/scope_registry.py`.
- Migrated Platform SDK action scope resolution to the canonical registry.
- Converted RBAC to scope-key permissions (`RolePermission.scope_key`) and updated role APIs to accept `permissions: string[]`.
- Added scope catalog endpoint: `GET /api/tenants/{tenant_slug}/scope-catalog`.
- Added tenant security bootstrap service to seed immutable default roles (`owner`, `admin`, `member`) and owner/member assignments.
- Changed new user default role to `user` (from `admin`) in register/google auth flows.
- Hardened tenant context dependency to require `X-Tenant-ID` (removed first-tenant fallback).
- Added workload provisioning service to provision agent principal/policy intent at config lifecycle.
- Enforced strict runtime delegation behavior:
  - No runtime principal/policy self-heal for agent runs.
  - Explicit delegation policy errors (`WORKLOAD_PRINCIPAL_MISSING`, `WORKLOAD_POLICY_PENDING`, `INSUFFICIENT_APPROVED_SCOPES`).
- Hardened internal auth delegation path to reject runtime dynamic agent principal creation.
- Migrated control-plane route enforcement to scope dependencies for:
  - models routes
  - knowledge stores routes
  - admin routes (users/threads/stats)
- Removed effective role-edit behavior from `PATCH /admin/users/{user_id}` (profile edits only).
- Updated frontend RBAC/admin wiring:
  - RBAC service now uses scope-key permissions.
  - Security page consumes scope catalog and scope-key matrices.
  - Users table removed global `user/admin` role dropdown and added RBAC assignment/revoke controls.

## Test Coverage Added
- Backend feature suites added:
  - `backend/tests/security_scope_registry/`
  - `backend/tests/security_rbac_scope_model/`
  - `backend/tests/security_bootstrap_defaults/`
  - `backend/tests/security_workload_provisioning/`
  - `backend/tests/security_route_enforcement/`
  - `backend/tests/security_admin_user_management/`
- Frontend feature suites added:
  - `frontend-reshet/src/__tests__/security_roles_scope_editor/`
  - `frontend-reshet/src/__tests__/admin_users_rbac_editor/`
  - `frontend-reshet/src/__tests__/security_workload_approvals/`
- Updated existing suites in:
  - `backend/tests/workload_delegation_auth/`
  - `backend/tests/platform_sdk_tool/`
  - `backend/tests/platform_architect_e2e/`

## Remaining Gaps for Next Wave
- Enforce non-empty agent graph validation at API level (start/end guarantees).
- Complete strict route unification across remaining legacy routers still using direct role checks.
- Expand frontend tests for Users RBAC modal interactions and Security page role editor flows.
- Add migration reporting tooling for role reset impact visibility per tenant.
