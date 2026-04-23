# Security Route Enforcement Test State

Last Updated: 2026-04-23

## Scope
Validate control-plane route scope enforcement and organization-context strictness.

## Test Files
- test_route_scope_enforcement.py

## Key Scenarios Covered
- `X-Organization-ID` required for organization-bound model routes
- Models list allowed with correct scope
- Cross-org `X-Organization-ID` overrides are rejected for non-platform-admin bearer principals
- Knowledge-store write denied for member without write scope
- `/api/organizations/{organization_id}` routes reject cross-org reads and mutations when the path org differs from the principal org

## Last Run
- Command: `pytest -q backend/tests/security_scope_registry backend/tests/role_assignments_model backend/tests/security_bootstrap_defaults backend/tests/security_workload_provisioning backend/tests/security_route_enforcement backend/tests/security_admin_user_management`
- Date/Time: 2026-03-05
- Result: pass
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/workos_native_auth/test_workos_native_auth_service.py backend/tests/workos_native_auth/test_auth_session_effective_scopes.py backend/tests/security_route_enforcement/test_route_scope_enforcement.py`
- Date/Time: 2026-04-23 Asia/Hebron
- Result: PASS (`15 passed`)

## Known Gaps
- Does not yet cover all models/knowledge-stores mutation endpoints.

## 2026-04-21 validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/organization_api_keys/test_api_keys_api.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py`
- Result: blocked by out-of-slice schema/model drift (`INSERT INTO organizations ... relation "organizations" does not exist`)

## 2026-04-21 tenant-to-organization validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/security_route_enforcement/test_route_scope_enforcement.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/settings_api_keys/test_settings_api_keys_api.py tests/admin_monitoring/test_admin_monitoring_api.py -q`
- Result: PASS (`13 passed`)
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py tests/organization_bootstrap/test_default_agent_profiles.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Result: PASS (`52 passed`)
