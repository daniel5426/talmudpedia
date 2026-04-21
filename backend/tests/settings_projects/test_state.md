# Settings Projects Backend Test State

Last Updated: 2026-04-21

## Scope
Canonical settings project list/detail/update endpoints.

## Test Files
- `test_settings_projects_api.py`

## Key Scenarios Covered
- Lists organization projects.
- Updates a project.
- Reads the project members view.

## Last Run
- Command: `SECRET_KEY=codex-settings-test-secret-key-123456 PYTHONPATH=backend ./.venv-settings-tests/bin/python -m pytest -q backend/tests/settings_profile/test_settings_profile_api.py backend/tests/settings_projects/test_settings_projects_api.py backend/tests/settings_api_keys/test_settings_api_keys_api.py backend/tests/settings_limits/test_settings_limits_api.py backend/tests/settings_audit/test_settings_audit_api.py backend/tests/settings_people_permissions/test_settings_people_permissions_api.py`
- Date/Time: 2026-04-19
- Result: Pass

## Known Gaps
- No project role-assignment-backed member case yet.

## 2026-04-21 project-create route validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/settings_projects/test_settings_projects_api.py -q`
- Result: PASS (`1 passed`)
- Coverage: verifies `POST /api/settings/projects`, then list, patch, and members by canonical `project_id`.
