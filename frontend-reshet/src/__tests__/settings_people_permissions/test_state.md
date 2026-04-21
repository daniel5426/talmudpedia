# Settings People & Permissions Test State

Last Updated: 2026-04-21

## Scope
Service contract for members, invitations, groups, roles, and role assignments in the canonical settings surface.

## Test Files
- `settings_people_permissions_service.test.ts`
- `settings_people_permissions_dialogs.test.tsx`
- `settings_people_permissions_section.test.tsx`

## Key Scenarios Covered
- Members endpoint wiring.
- Invitation create endpoint wiring, including project role id.
- Group create endpoint wiring.
- Role create/update endpoint wiring with family-aware payloads.
- Role assignment delete endpoint wiring.
- Role editor renders family-specific permission resources.
- Member access editor renders organization role and project access sections.
- People & Permissions section renders assignment-derived organization roles from the members payload.

## Last Run
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/settings_people_permissions/settings_people_permissions_service.test.ts src/__tests__/settings_people_permissions/settings_people_permissions_dialogs.test.tsx src/__tests__/settings_people_permissions/settings_people_permissions_section.test.tsx --watch=false`
- Date: 2026-04-21
- Result: pass (`3 suites, 5 tests`)

## Known Gaps
- No browser-level end-to-end People & Permissions flow yet.
