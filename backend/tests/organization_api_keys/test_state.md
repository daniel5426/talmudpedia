# Organization API Keys Tests

Last Updated: 2026-04-21

Scope:
- Organization-scoped API-key admin routes for create, list, and revoke.
- Secret visibility guarantees for API-key creation flows.

Test files present:
- test_api_keys_api.py

Key scenarios covered:
- Create returns bearer token material once alongside stored key metadata.
- List returns stored metadata without replaying secret material.
- Revoke transitions key status to `revoked`.

Last run command: `cd backend && PYTHONPATH=. pytest -q tests/organization_api_keys/test_api_keys_api.py tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py tests/control_plane_sdk tests/published_apps_external_runtime/test_external_runtime_api.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py tests/security_scope_registry/test_scope_registry.py`
Last run date/time: 2026-03-16 19:38 EET
Last run result: pass (`45 passed, 2 skipped`)

Known gaps / follow-ups:
- Add admin authorization failure coverage for missing `api_keys.*` scopes if those routes broaden beyond owner/admin defaults.

## 2026-04-21 tenant-to-organization validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/organization_api_keys/test_api_keys_api.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/admin_monitoring/test_admin_monitoring_api.py -q`
- Result: PASS (`13 passed`)
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py tests/platform_architect_runtime/test_native_platform_assets_actions.py tests/platform_native_adapter/test_platform_native_adapter.py tests/organization_bootstrap/test_default_agent_profiles.py tests/settings_api_keys/test_settings_api_keys_api.py tests/organization_api_keys/test_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py tests/tool_execution/test_function_tool_execution.py tests/tool_execution/test_agent_call_tool_execution.py -q`
- Result: PASS (`98 passed`)
