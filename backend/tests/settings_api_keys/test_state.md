# Settings API Keys Backend Test State

Last Updated: 2026-04-19

## Scope
Canonical organization and project API key endpoints.

## Test Files
- `test_settings_api_keys_api.py`

## Key Scenarios Covered
- Creates and lists organization API keys.
- Creates and revokes project API keys.
- Deletes organization API keys.

## Last Run
- Command: `SECRET_KEY=codex-settings-test-secret-key-123456 PYTHONPATH=backend ./.venv-settings-tests/bin/python -m pytest -q backend/tests/settings_profile/test_settings_profile_api.py backend/tests/settings_projects/test_settings_projects_api.py backend/tests/settings_api_keys/test_settings_api_keys_api.py backend/tests/settings_limits/test_settings_limits_api.py backend/tests/settings_audit/test_settings_audit_api.py backend/tests/settings_people_permissions/test_settings_people_permissions_api.py`
- Date/Time: 2026-04-19
- Result: Pass

## Known Gaps
- Missing authorization failure coverage for scoped key operations.
