# Admin Monitoring Test State

Last Updated: 2026-04-22

## Scope
Validate the unified monitored-users read model, thread attribution, and agent-scoped stats behavior for admin monitoring.

## Test Files
- test_admin_monitoring_api.py

## Key Scenarios Covered
- Mapped published-app accounts merge into the platform user actor
- Unmapped published-app accounts remain standalone monitored actors
- Embedded identities remain separate per `agent_id + external_user_id`
- Actor thread history includes merged mapped-account threads
- Thread list exposes actor and agent attribution and filters by agent
- Thread list includes explicit lineage metadata for root/child grouping in the admin threads table
- Thread detail joins canonical per-run usage onto each turn and exposes thread total tokens
- Thread detail now splits exact usage from estimated fallback usage instead of presenting one ambiguous total
- Admin thread detail resolves the same project-scoped threads that appear in the admin threads table.
- Agent stats can scope to a single agent and keep merged actor counts
- Resource stats serialize slugless model-registry rows without crashing the admin stats summary

## Last Run
- Command: `PYTHONPATH=. pytest -q backend/tests/admin_monitoring/test_admin_monitoring_api.py`
- Date/Time: 2026-03-29 Asia/Hebron
- Result: PASS (`7 passed, 7 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/admin_monitoring/test_admin_monitoring_api.py`
- Date/Time: 2026-04-06 Asia/Hebron
- Result: PASS (`8 passed, 8 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_threads/test_thread_service.py backend/tests/admin_monitoring/test_admin_monitoring_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-03-27 Asia/Hebron
- Result: PASS (`17 passed`)

## Known Gaps
- Does not yet cover dashboard overview payload or frontend rendering.

## 2026-04-21 validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py -q`
- Result: PASS (`8 passed`)
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py tests/organization_bootstrap/test_default_agent_profiles.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Result: PASS (`52 passed`)

## 2026-04-22 validation
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/admin_monitoring/test_admin_monitoring_api.py`
- Result: PASS (`9 passed`)
