Last Updated: 2026-04-21

# WorkOS Native Auth Test State

## Scope
- Verify backend WorkOS auth service uses the native Python SDK session helpers.
- Cover native `load_sealed_session`, `session.refresh()`, and `authenticate_with_code()` integration points.
- Verify browser control-plane effective scopes ignore WorkOS permission payload drift.

## Test Files Present
- `test_workos_native_auth_service.py`
- `test_auth_session_effective_scopes.py`

## Key Scenarios Covered
- Expired session path loads the sealed session via the native helper and rotates the cookie with native refresh.
- Auth code exchange uses the native typed `authenticate_with_code()` API and passes session sealing config.
- Concurrent expired-session requests coalesce to a single native refresh and share the rotated cookie result.
- `/auth/session` resolves the same local `effective_scopes` even when WorkOS permission payloads vary.

## Last Run
- 2026-04-21: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/settings_people_permissions/test_settings_people_permissions_api.py backend/tests/workos_native_auth/test_auth_session_effective_scopes.py backend/tests/security_route_enforcement/test_route_scope_enforcement.py backend/tests/settings_api_keys/test_settings_api_keys_api.py backend/tests/admin_monitoring/test_admin_monitoring_api.py` -> `14 passed`
- 2026-04-19: `SECRET_KEY=explicit-test-secret-0123456789abcdef TEST_USE_REAL_DB=0 backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/workos_native_auth/test_workos_native_auth_service.py` -> `2 passed`
- 2026-04-19: `SECRET_KEY=explicit-test-secret-0123456789abcdef TEST_USE_REAL_DB=0 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest -q backend/tests/workos_native_auth/test_workos_native_auth_service.py` -> `2 passed`
- 2026-04-19: `SECRET_KEY=explicit-test-secret-0123456789abcdef TEST_USE_REAL_DB=0 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest -q backend/tests/workos_native_auth/test_workos_native_auth_service.py` -> `3 passed`
- 2026-04-20: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/workos_native_auth/test_workos_native_auth_service.py backend/tests/workos_native_auth/test_auth_session_effective_scopes.py` -> `4 passed`

## Known Gaps
- Does not hit live WorkOS.
- Does not exercise the full browser callback flow end-to-end.

## 2026-04-21 tenant-to-organization validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/workos_native_auth/test_auth_session_effective_scopes.py tests/settings_api_keys/test_settings_api_keys_api.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/admin_monitoring/test_admin_monitoring_api.py -q`
- Result: PASS (`13 passed`)
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py tests/organization_bootstrap/test_default_agent_profiles.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Result: PASS (`52 passed`)
