# Test State: Published Apps External Runtime

Last Updated: 2026-04-20

## Scope
- Host-anywhere published-app runtime surface under `/public/external/apps/*`.
- Bearer-token published-app auth for externally hosted browser clients.
- External runtime bootstrap, chat streaming, and persisted thread/history APIs.
- Origin allowlist enforcement for external published-app traffic.

## Test Files Present
- `backend/tests/published_apps_external_runtime/test_external_runtime_api.py`

## Key Scenarios Covered
- External bootstrap returns the new runtime surface and CORS headers.
- External password auth returns bearer tokens and supports `me` and `logout`.
- External bearer tokens cannot be replayed across published apps.
- External runtime routes reject bearer tokens that are missing required published-app scopes.
- External OIDC exchange returns a bearer session token.
- External authenticated stream persists threads and exposes list/detail history APIs.
- External authenticated stream replays persisted worker-owned run events instead of executing in the request path.
- External thread detail remains app-account scoped.
- External thread detail can return nested `lineage` and `subthread_tree` payloads when `include_subthreads=true`.
- Auth-disabled apps stream ephemerally with no persisted thread.
- Disallowed origins are rejected on the external runtime surface.

## Last Run Command + Date/Time + Result
- Command: `TEST_USE_REAL_DB=0 /Users/danielbenassaya/Code/personal/talmudpedia/backend/.venv-codex-tests/bin/python -m pytest -q backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-04-19 Asia/Hebron
- Result: PASS (`22 passed`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/published_apps/test_admin_apps_crud.py backend/tests/published_apps/test_public_app_resolve_and_config.py backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py backend/tests/workos_native_auth/test_auth_session_effective_scopes.py backend/tests/settings_api_keys/test_settings_api_keys_api.py`
- Date/Time: 2026-04-20 23:17 EEST
- Result: PASS (`41 passed`, includes external runtime coverage)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-04-05 Asia/Hebron
- Result: PASS (`17 passed`)
- Command: `TEST_USE_REAL_DB=0 PYTHONPATH=backend python3 -m pytest -q backend/tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py backend/tests/published_apps/test_public_chat_scope_and_persistence.py backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date/Time: 2026-04-09 Asia/Hebron
- Result: PASS (`26 passed`)

## Known Gaps or Follow-ups
- Add explicit preflight `OPTIONS` coverage for allowed and blocked origins.
