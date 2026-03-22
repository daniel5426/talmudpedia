# Published Apps Backend Tests

Last Updated: 2026-03-23

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
- Apps admin page fetch contract is probe-covered for `/admin/apps`, `/admin/apps/stats`, `/agents?limit=500&compact=true`, `/admin/apps/templates`, and `/admin/apps/auth/templates`.
- Published-app analytics coverage verifies bootstrap view capture, 30-minute visit dedupe, authenticated bootstrap attribution, and `/admin/apps/stats` aggregation.
- Initial app-create draft revision (`origin_kind=app_init`) auto-enqueues async build; enqueue failure marks revision build failed without blocking app creation.
- Builder state includes app + template + current draft metadata.
- Admin export options/archive exposes standalone export readiness and packages the current draft or live workspace snapshot.
- Canonical app-create and builder tests use `template_key="classic-chat"`.
- Template catalog ignores non-pack directories and returns an empty list when no valid manifest-backed packs exist.
- Template catalog verifies the materialized classic-chat runtime overlay includes the shared `resolveRuntimeBasePath` export and attachment-aware `RuntimeInput`.
- Public runtime/config endpoints enforce visibility and auth constraints.
- Path-mode published auth/chat/runtime endpoints are removed (`410`), while admin user-management tests use host-runtime auth (`/_talmudpedia/*`).
- Public preview stream uses token auth and persists run-native thread records.
- Runtime bootstrap contract includes `request_contract_version=thread.v1`.
- Agent integration contract payload is exposed and validated.
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

## Known gaps or follow-ups
- Add explicit regression tests for removed `/admin/apps/{app_id}/publish` route in this folder (currently covered under `backend/tests/app_versions/`).
- Add expanded negative tests for cross-app preview token replay and long-lived preview auth refresh behavior.
- Run the new `real_db` apps-page fetch probe regularly against the local tenant to catch latency regressions on real data volume.
