# Settings API Keys Backend Test State

Last Updated: 2026-04-21

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

## 2026-04-21 validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/settings_api_keys/test_settings_api_keys_api.py`
- Result: `1 passed`

## 2026-04-21 helper-layer follow-up
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/organization_api_keys/test_api_keys_api.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py`
- Result: blocked by out-of-slice schema/model drift (`Organization` now points at `organizations`, but the test DB still does not have that table)

## 2026-04-21 tenant-to-organization validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/admin_monitoring/test_admin_monitoring_api.py -q`
- Result: PASS (`13 passed`)
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py tests/organization_bootstrap/test_default_agent_profiles.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Result: PASS (`52 passed`)
