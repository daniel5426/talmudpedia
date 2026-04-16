# Published Apps Backend Tests

Last Updated: 2026-04-16

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
- Tenant admin can create/list/update/delete apps.
- Apps admin page fetch contract is probe-covered for `/admin/apps`, `/admin/apps/stats`, `/agents?limit=500&view=summary`, `/admin/apps/templates`, and `/admin/apps/auth/templates`.
- Published-app analytics coverage verifies bootstrap view capture, 30-minute visit dedupe, authenticated bootstrap attribution, and `/admin/apps/stats` aggregation.
- App creation provisions the shared draft workspace, materializes the first durable `app_init` draft revision, and fails when initial watcher-owned materialization fails.
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
- Agent integration contract payload is exposed and validated.
- Agent integration contract exposes `frontend_requirements` for frontend-dependent tools such as the new built-in `UI Blocks` tool, including installer command metadata.
- Legacy publish helper now routes publish through selected version flow.

## Last run command + date/time + result
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/published_apps/test_admin_apps_crud.py`
- Date: 2026-03-15
- Result: PASS (6 passed, 6 warnings)
- Command: `cd backend && PYTHONPATH=. pytest -x -q tests/published_apps/test_public_app_resolve_and_config.py tests/published_apps/test_public_chat_scope_and_persistence.py tests/published_apps/test_builder_agent_integration_contract.py tests/published_apps/test_template_catalog.py`
- Date: 2026-03-15
- Result: FAIL (`test_preview_asset_proxy_streams_dist_asset` expects `published_app_preview_token`, but runtime now sets `published_app_public_preview_token`)
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

## Known gaps or follow-ups
- Add explicit regression tests for removed `/admin/apps/{app_id}/publish` route in this folder (currently covered under `backend/tests/app_versions/`).
- Add expanded negative tests for cross-app preview token replay and long-lived preview auth refresh behavior.
- Run the new `real_db` apps-page fetch probe regularly against the local tenant to catch latency regressions on real data volume.
