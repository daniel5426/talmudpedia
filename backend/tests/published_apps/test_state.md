# Published Apps Backend Tests

Last Updated: 2026-04-23

## Scope of the feature
- Admin CRUD for published apps and builder state primitives.
- Public runtime resolve/config/runtime/chat endpoint behavior.
- Agent-integration contract exposure for builder.
- Hard-cut publish flow support through `/versions/{version_id}/publish` helpers.

## Test files present
- `backend/tests/published_apps/test_admin_apps_crud.py`
- `backend/tests/published_apps/test_admin_app_export.py`
- `backend/tests/published_apps/test_admin_apps_page_fetch_probe.py`
- `backend/tests/published_apps/test_app_stats_api.py`
- `backend/tests/published_apps/test_builder_agent_integration_contract.py`
- `backend/tests/published_apps/test_template_catalog.py`
- `backend/tests/published_apps/test_public_app_resolve_and_config.py`
- `backend/tests/published_apps/test_public_chat_scope_and_persistence.py`

## Key scenarios covered
- Organization admin can create/list/update/delete apps.
- Apps admin page fetch contract is probe-covered for `/admin/apps`, `/admin/apps/stats`, `/agents?limit=500&view=summary`, `/admin/apps/templates`, and `/admin/apps/auth/templates`.
- Published-app analytics coverage verifies bootstrap view capture, 30-minute visit dedupe, authenticated bootstrap attribution, and `/admin/apps/stats` aggregation.
- App creation is fast and does not seed a fake draft revision; builder `ensure` now returns after provisioning the live workspace/session, and the first durable `app_init` revision is created asynchronously after the first watcher-ready build exists.
- Builder state includes app + template + current draft metadata.
- Admin export options/archive exposes standalone export readiness and packages the current draft or live workspace snapshot.
- Canonical app-create and builder tests use `template_key="classic-chat"`.
- Template catalog ignores non-pack directories and returns an empty list when no valid manifest-backed packs exist.
- Template catalog verifies the materialized classic-chat runtime overlay includes the shared `resolveRuntimeBasePath` export and attachment-aware `RuntimeInput`.
- Public runtime/config endpoints enforce visibility and auth constraints.
- Path-mode published auth/chat/runtime endpoints are removed (`410`), while admin user-management tests use host-runtime auth (`/_talmudpedia/*`).
- Public preview stream uses token auth and persists run-native thread records.
- Public preview stream now attaches to persisted worker-owned run events instead of executing in the request path.
- Runtime bootstrap contract includes `request_contract_version=thread.v1`.
- Preview runtime/bootstrap now uses the canonical `published_app_preview_token` cookie and bootstrap-ready `preview_url`.
- Preview HTML asset rewrites now canonicalize to absolute preview asset paths under `/public/apps/preview/revisions/{revision_id}/assets/...`.
- App-create test setup uses the shared create/materialize stub instead of booting a real draft-dev sandbox.
- Agent integration contract payload is exposed and validated.
- Agent integration contract exposes `frontend_requirements` for frontend-dependent tools such as the new built-in `UI Blocks` tool, including installer command metadata.
- Legacy publish helper now routes publish through selected version flow.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/published_apps/test_admin_apps_crud.py`
- Date: 2026-03-15
- Result: PASS (6 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps/test_public_chat_scope_and_persistence.py tests/published_apps/test_builder_agent_integration_contract.py tests/published_apps/test_template_catalog.py`
- Date: 2026-03-15
- Result: Historical FAIL before the unified preview-auth cleanup (`test_preview_asset_proxy_streams_dist_asset` drifted on the old split preview-cookie contract)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/published_apps/test_admin_apps_page_fetch_probe.py`
- Date: 2026-03-22
- Result: PASS (`-k smoke`: 1 passed, 1 deselected, 7 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/published_apps/test_template_catalog.py`
- Date: 2026-03-22
- Result: PASS (3 passed, 1 warning)
- Command: `pytest -q backend/tests/published_apps/test_template_catalog.py`
- Date: 2026-03-23
- Result: PASS (4 passed, 1 warning)
- Command: `cd backend && PYTHONPATH=. pytest -q tests/published_apps/test_admin_app_export.py`
- Date: 2026-03-22
- Result: PASS (2 passed, 7 warnings)
- Command: `pytest -q backend/tests/published_apps/test_app_stats_api.py backend/tests/published_apps/test_admin_apps_page_fetch_probe.py`
- Date: 2026-03-22
- Result: PASS (4 passed, 1 skipped)
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia/backend python3 -m pytest -q /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/builtin_tools_registry/test_builtin_registry_api.py /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/published_apps/test_builder_agent_integration_contract.py /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/builtin_tool_execution/test_builtin_tool_executor.py`
- Date: 2026-03-30
- Result: PASS (28 passed, 7 warnings)
- Command: `TEST_USE_REAL_DB=0 PYTHONPATH=backend python3 -m pytest -q backend/tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py backend/tests/published_apps/test_public_chat_scope_and_persistence.py backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Date: 2026-04-09
- Result: PASS (`26 passed`, detached stream regression suite)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest backend/tests/published_apps/test_admin_apps_crud.py backend/tests/published_apps/test_public_app_resolve_and_config.py backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py backend/tests/workos_native_auth/test_auth_session_effective_scopes.py backend/tests/settings_api_keys/test_settings_api_keys_api.py`
- Date: 2026-04-20 23:17 EEST
- Result: PASS (`41 passed`)

- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py tests/published_apps/test_admin_apps_crud.py`
- Date: 2026-04-21 Asia/Hebron
- Result: PASS (`30 passed`). Published-app host/runtime/export contracts now use `public_id` instead of slug-era identity throughout the touched paths.

## Known gaps or follow-ups
- Add explicit regression tests for removed `/admin/apps/{app_id}/publish` route in this folder (currently covered under `backend/tests/app_versions/`).
- Add expanded negative tests for cross-app preview token replay and long-lived preview auth refresh behavior.
- Run the new `real_db` apps-page fetch probe regularly against the local tenant to catch latency regressions on real data volume.

## 2026-04-21 tenant-to-organization validation
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Result: PASS (`34 passed`)
- Command: `cd backend && SECRET_KEY=explicit-test-secret .venv/bin/python -m pytest tests/admin_monitoring/test_admin_monitoring_api.py tests/graph_mutation_agents/test_agent_graph_mutation_routes.py tests/platform_architect_runtime/test_native_platform_tools.py tests/organization_bootstrap/test_default_agent_profiles.py tests/settings_api_keys/test_settings_api_keys_api.py tests/workos_native_auth/test_auth_session_effective_scopes.py tests/security_route_enforcement/test_route_scope_enforcement.py tests/published_apps/test_admin_apps_crud.py tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py -q`
- Result: PASS (`52 passed`)

## 2026-04-21 published-app project scoping
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/published_apps/test_admin_apps_crud.py backend/tests/published_apps/test_public_app_resolve_and_config.py backend/tests/published_apps_external_runtime/test_external_runtime_api.py backend/tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py`
- Result: PASS (`39 passed`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py backend/tests/published_apps/test_public_app_resolve_and_config.py backend/tests/sandbox_controller/test_dev_shim.py backend/tests/sandbox_controller/test_draft_dev_runtime_client_stream.py backend/tests/app_versions/test_versions_endpoints.py`
- Date: 2026-04-23 Asia/Hebron
- Result: PASS (`40 passed`). Revision preview runtime and preview asset bootstrap now match the unified preview-auth cookie/query contract.

## 2026-04-23 apps-builder async first-version bootstrap
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/published_apps/test_admin_apps_crud.py -k 'create_returns_no_draft_until_first_real_build or ensure_session_bootstraps_live_workspace_without_inline_app_init_revision'`
- Result: PASS (`2 passed`). App create stays revision-less, `builder/draft-dev/session/ensure` now returns with a live workspace session before `Version 1`, and the initial `app_init` version is detached from the request critical path.
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/published_apps/test_admin_apps_crud.py backend/tests/apps_builder_sandbox_runtime/test_runtime_client_and_preview_proxy.py backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py -k 'test_admin_apps_crud or test_admin_app_create_returns_no_draft_until_first_real_build or test_admin_app_ensure_session_bootstraps_live_workspace_without_inline_app_init_revision or test_builder_preview_ or test_ensure_endpoint_reuses_live_session_without_calling_legacy_ensure_session or test_heartbeat_preserves_existing_preview_base_path_when_refresh_returns_root'`
- Result: PASS (`22 passed`). The async first-version bootstrap path and revision-less builder preview bootstrap are covered together with the touched admin CRUD and preview proxy flows.
