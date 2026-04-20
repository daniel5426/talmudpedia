# Settings People & Permissions Test State

Last Updated: 2026-04-20

## Scope
Service contract for members, invitations, groups, roles, and role assignments in the canonical settings surface.

## Test Files
- `settings_people_permissions_service.test.ts`
- `settings_people_permissions_dialogs.test.tsx`

## Key Scenarios Covered
- Members endpoint wiring.
- Invitation create endpoint wiring.
- Group create endpoint wiring.
- Role create/update endpoint wiring with family-aware payloads.
- Role assignment delete endpoint wiring.
- Role editor renders family-specific permission resources.
- Member org-role editor remains single-select.

## Last Run
- Command: `pnpm test -- --runTestsByPath src/__tests__/settings_people_permissions/settings_people_permissions_service.test.ts src/__tests__/settings_people_permissions/settings_people_permissions_dialogs.test.tsx`
- Date: 2026-04-20
- Result: Not run after latest custom-role UI edits

## Known Gaps
- No full People & Permissions tab integration test yet.
