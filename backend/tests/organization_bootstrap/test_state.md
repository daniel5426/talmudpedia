# Organization Bootstrap Tests

Last Updated: 2026-04-21

## Scope

Validates organization/project bootstrap materialization of default agent profiles after the hard-cut removal of startup tenant scanning.

## Test Files Present

- `backend/tests/organization_bootstrap/test_default_agent_profiles.py`

## Key Scenarios Covered

- organization creation creates the canonical platform architect profile
- default project bootstrap creates coding-agent profiles
- seeded default agent profiles validate against the current model registry
- platform architect defaults to `architect_mode=default` when none is provided
- additional project creation does not duplicate default profiles
- existing organizations can be backfilled through explicit ensure helpers without startup seeding
- `/agents` lazy backfill persists seeded profiles across requests instead of returning transient IDs
- `/agents` skips bootstrap writes once the canonical default profiles already exist for the tenant

## Last Run

- Command: `python3 -m pytest backend/tests/organization_bootstrap/test_default_agent_profiles.py -q`
- Date: 2026-04-14
- Result: Not run yet after latest change
- Command: `python3 -m pytest backend/tests/organization_bootstrap/test_default_agent_profiles.py backend/tests/platform_architect_runtime/test_architect_seeding.py -q`
- Date: 2026-04-14
- Result: Pass (`7 passed`)
- Command: `cd backend && PYTHONPATH=. python3 -m pytest -q tests/organization_bootstrap/test_default_agent_profiles.py`
- Date: 2026-04-14
- Result: PASS
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/platform_architect_runtime/test_native_platform_assets_actions.py tests/platform_architect_runtime/test_native_platform_tools.py tests/platform_native_adapter/test_platform_native_adapter.py tests/organization_bootstrap/test_default_agent_profiles.py`
- Date: 2026-04-21 Asia/Hebron
- Result: Pass (`18 passed, 6 warnings`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/organization_bootstrap/test_default_agent_profiles.py backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_tools.py backend/tests/settings_people_permissions/test_settings_people_permissions_api.py backend/tests/graph_mutation_agents/test_agent_graph_mutation_routes.py backend/tests/rag_extreme_campaign/test_admin_graph_and_jobs_api.py backend/tests/artifact_runtime/test_artifact_versions_api.py`
- Date: 2026-04-21 Asia/Hebron
- Result: Pass (`30 passed`). Default-profile seeding remains green after the internal row-key/system-key hard cut.

## Known Gaps

- legacy tenant-era agent APIs outside bootstrap/list flows are not covered here

## 2026-04-21 validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/organization_bootstrap/test_default_agent_profiles.py`
- Result: `5 passed`

## 2026-04-21 tenant-to-organization validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/organization_bootstrap/test_default_agent_profiles.py tests/platform_architect_runtime/test_native_platform_assets_actions.py tests/platform_architect_runtime/test_native_platform_tools.py tests/platform_native_adapter/test_platform_native_adapter.py`
- Result: PASS (`18 passed, 6 warnings`)
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py tests/organization_bootstrap/test_default_agent_profiles.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Result: PASS (`52 passed`)

## 2026-04-21 seeded-agent drift validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/organization_bootstrap/test_default_agent_profiles.py -q`
- Date: 2026-04-21 17:37 EEST
- Result: PASS (`6 passed, 6 warnings`)
