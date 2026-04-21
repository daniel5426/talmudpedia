Last Updated: 2026-04-21

# Test State: Published Apps Host Runtime (Same-URL Auth Gate)

## Scope
Backend same-URL published app host runtime flow for `*.apps` domains:
- same-URL auth shell render
- cookie-based signup/auth state
- cookie-protected chat stream access
- thread persistence with host runtime endpoint

## Test Files Present
- `backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`

## Key Scenarios Covered
- Unauthenticated root request on app host renders branded auth shell HTML
- Signup on `/_talmudpedia/auth/signup` sets `published_app_session` cookie
- `/_talmudpedia/auth/state` reflects authenticated user from cookie
- Same email can sign up in two published apps and gets two distinct app-account records
- `/_talmudpedia/chat/stream` requires auth when `auth_enabled=true`
- Authenticated `/_talmudpedia/chat/stream` streams and returns `X-Thread-ID`
  - Signed-up host users are granted tenant member RBAC assignment in test setup so delegated run scopes intersect correctly under strict runtime delegation
- Host chat stream now attaches to persisted worker-owned run events instead of executing in the request path
- Host runtime history endpoints: `GET /_talmudpedia/threads`, `GET /_talmudpedia/threads/{thread_id}`
- Host runtime thread detail is enforced by app-account ownership, not just app scope
- Host runtime rejects replaying a session cookie on a different published-app host.
- Host runtime rejects session cookies that are missing required published-app scopes.
- Host password login throttles repeated failed attempts with `429`.
- Host Google OAuth start sets an anti-CSRF state cookie, and callback rejects missing state cookies.
- Host runtime thread detail includes canonical persisted `response_blocks`; `run_events` are secondary debug/history data
- Host runtime thread detail now patches the canonical runtime-surface event projection path rather than a route-local wrapper seam
- Host runtime thread detail can return nested `lineage` and `subthread_tree` payloads when `include_subthreads=true`
- Legacy `/public/apps/{slug}` published runtime/auth/chat endpoints return `410`
- Auth-gated host assets are served with private cache headers.

## Last Run
- Command: `SECRET_KEY=explicit-test-secret-0123456789abcdef TEST_USE_REAL_DB=0 /Users/danielbenassaya/Code/personal/talmudpedia/backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-04-19 Asia/Hebron
- Result: PASS (`16 passed`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/published_apps/test_admin_apps_crud.py backend/tests/published_apps/test_public_app_resolve_and_config.py backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py backend/tests/workos_native_auth/test_auth_session_effective_scopes.py backend/tests/settings_api_keys/test_settings_api_keys_api.py`
- Date/Time: 2026-04-20 23:17 EEST
- Result: PASS (`41 passed`, includes host-runtime coverage)
- Command: `SECRET_KEY=test-secret-key PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -k 'test_host_thread_detail_includes_public_run_events'`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: PASS (`1 passed`)
- Command: `TEST_USE_REAL_DB=0 /Users/danielbenassaya/Code/personal/talmudpedia/backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-04-19 Asia/Hebron
- Result: PASS (`22 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/agent_threads/test_thread_service.py backend/tests/admin_monitoring/test_admin_monitoring_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-03-27 Asia/Hebron
- Result: PASS (`17 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-04-05 Asia/Hebron
- Result: PASS (`17 passed`)
- Command: `TEST_USE_REAL_DB=0 PYTHONPATH=backend python3 -m pytest -q backend/tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py backend/tests/published_apps/test_public_chat_scope_and_persistence.py backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-04-09 Asia/Hebron
- Result: PASS (`26 passed`)
- Command: `pytest -q backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-03-22 (local run)
- Result: PASS (`9 passed`, `7 warnings`)
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-03-15 (local run)
- Result: PASS (8 passed, 6 warnings)
- Command: `pytest -q backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py backend/tests/published_apps/test_public_chat_scope_and_persistence.py backend/tests/published_apps/test_admin_apps_crud.py`
- Date/Time: 2026-03-09 (local run)
- Result: pass (`14 passed`)

## Known Gaps / Follow-ups
- No host asset/document authenticated bundle-serving tests yet (requires revision + bundle storage mocking)
- No external OIDC exchange host tests yet
- No stale/invalid cookie auto-clear tests yet
- No host-side archive endpoint tests yet

## 2026-04-21 tenant-to-organization validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps/test_admin_apps_crud.py -q`
- Result: PASS (`34 passed`)
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py tests/organization_bootstrap/test_default_agent_profiles.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Result: PASS (`52 passed`)
