# Settings People & Permissions Backend Test State

Last Updated: 2026-04-20

## Scope
Canonical members, invitations, groups, roles, and assignments endpoints under `/api/settings/people/*`.

## Test Files
- `test_settings_people_permissions_api.py`

## Key Scenarios Covered
- Lists members.
- Lists, creates, and revokes invitations, including persisted project-role selection.
- Creates groups.
- Creates organization and project custom roles.
- Rejects invalid family/assignment-kind combinations.
- Rejects preset role edit/delete.
- Rejects deleting a role referenced by a pending invite.
- Replaces prior organization role assignments for the same member and assignment kind.

## Last Run
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/settings_people_permissions/test_settings_people_permissions_api.py`
- Date/Time: 2026-04-20
- Result: pass (1 test)

## Known Gaps
- No group update/delete coverage yet.
