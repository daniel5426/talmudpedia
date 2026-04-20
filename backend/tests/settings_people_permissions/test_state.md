# Settings People & Permissions Backend Test State

Last Updated: 2026-04-20

## Scope
Canonical members, invitations, groups, roles, and assignments endpoints under `/api/settings/people/*`.

## Test Files
- `test_settings_people_permissions_api.py`

## Key Scenarios Covered
- Lists members.
- Lists, creates, and revokes invitations.
- Creates groups.
- Creates organization and project custom roles.
- Rejects invalid family/scope combinations.
- Rejects preset role edit/delete.
- Replaces prior organization role assignments for the same member and scope.

## Last Run
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/settings_people_permissions/test_settings_people_permissions_api.py`
- Date/Time: 2026-04-20
- Result: Not run after latest custom-role coverage edits

## Known Gaps
- No group update/delete coverage yet.
