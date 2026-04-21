# Settings People & Permissions Backend Test State

Last Updated: 2026-04-21

## Scope
Canonical members, invitations, groups, roles, and assignments endpoints under `/api/settings/people/*`.

## Test Files
- `test_settings_people_permissions_api.py`

## Key Scenarios Covered
- Lists members.
- Returns assignment-derived organization roles in members and project-members payloads.
- Lists, creates, and revokes invitations, including persisted project-role selection.
- Creates groups.
- Creates organization and project custom roles.
- Rejects invalid family/assignment-kind combinations.
- Rejects preset role edit/delete.
- Rejects deleting a role referenced by a pending invite.
- Rejects role assignment for non-members.
- Rejects direct deletion of organization-family assignments.
- Replaces prior organization role assignments for the same member and assignment kind.
- Enforces project-owner-only boundaries for project settings, project members, project API keys, and publish actions.
- Removes all in-org role assignments when organization membership is removed.

## Last Run
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/settings_people_permissions/test_settings_people_permissions_api.py backend/tests/workos_native_auth/test_auth_session_effective_scopes.py backend/tests/security_route_enforcement/test_route_scope_enforcement.py backend/tests/settings_api_keys/test_settings_api_keys_api.py backend/tests/admin_monitoring/test_admin_monitoring_api.py`
- Date/Time: 2026-04-21
- Result: pass (`14 passed`)

## Known Gaps
- No group update/delete coverage yet.
- No dedicated WorkOS invite-acceptance test yet for Reader plus optional project access through canonical assignment creation.
