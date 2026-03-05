# Security Roles Scope Editor Test State

Last Updated: 2026-03-05

## Scope
Validate frontend RBAC service scope-key role editor API wiring.

## Test Files
- rbac_scope_catalog.test.ts

## Key Scenarios Covered
- Scope catalog endpoint wiring
- Role create request sends scope-key permissions

## Last Run
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/security_roles_scope_editor src/__tests__/admin_users_rbac_editor src/__tests__/security_workload_approvals`
- Date/Time: 2026-03-05
- Result: pass

## Known Gaps
- Does not validate full Security page UI interactions.
