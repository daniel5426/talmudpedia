# Admin Users RBAC Editor Test State

Last Updated: 2026-03-05

## Scope
Validate frontend admin user update API payload behavior after role-edit removal.

## Test Files
- admin_service_user_update.test.ts

## Key Scenarios Covered
- User update request sends profile fields only

## Last Run
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/security_roles_scope_editor src/__tests__/admin_users_rbac_editor src/__tests__/security_workload_approvals`
- Date/Time: 2026-03-05
- Result: pass

## Known Gaps
- Does not yet test interactive role assignment dialog behavior in Users table.
