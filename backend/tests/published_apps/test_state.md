# Published Apps Backend Tests

Last Updated: 2026-03-01

## Scope of the feature
- Admin CRUD for published apps and builder state primitives.
- Public runtime resolve/config/runtime/chat endpoint behavior.
- Agent-integration contract exposure for builder.
- Hard-cut publish flow support through `/versions/{version_id}/publish` helpers.

## Test files present
- `backend/tests/published_apps/test_admin_apps_crud.py`
- `backend/tests/published_apps/test_builder_agent_integration_contract.py`
- `backend/tests/published_apps/test_public_app_resolve_and_config.py`
- `backend/tests/published_apps/test_public_chat_scope_and_persistence.py`

## Key scenarios covered
- Tenant admin can create/list/update/delete apps.
- Initial app-create draft revision (`origin_kind=app_init`) auto-enqueues async build; enqueue failure marks revision build failed without blocking app creation.
- Builder state includes app + template + current draft metadata.
- Public runtime/config endpoints enforce visibility and auth constraints.
- Public chat persistence and scoping behavior.
- Agent integration contract payload is exposed and validated.
- Legacy publish helper now routes publish through selected version flow.

## Last run command + date/time + result
- Command: `cd backend && pytest tests/published_apps/test_admin_apps_crud.py -k "initial_revision_build"`
- Date: 2026-03-01
- Result: PASS (2 passed, 4 deselected)

## Known gaps or follow-ups
- Add explicit regression tests for removed `/admin/apps/{app_id}/publish` route in this folder (currently covered under `backend/tests/app_versions/`).
- Add expanded negative tests for cross-app preview token replay and long-lived preview auth refresh behavior.
