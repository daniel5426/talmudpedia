# Base44 Config Migration Plan

Last Updated: 2026-02-15

## Scope
- Implement Config IA migration (`Preview | Config`) with sections: Overview, Users, Domains, Code.
- Add template-based auth UI selection and app branding fields.
- Add app visibility controls (`public`/`private`) and visibility gating on public runtime APIs.
- Add published-app users management (list + block/unblock).
- Add custom domains request tracking (`pending` workflow only).
- Keep Base44-like custom app data as a next phase (spec-only).

## Decisions Locked
- Visibility is stored as a dedicated field (`public|private`) separate from lifecycle status.
- Private means public runtime is not reachable.
- Auth templates are selectable at create time and editable later.
- Auth customization for this phase is template + branding only.
- Users tab ships list + block/unblock.
- Domains tab ships request tracking only (no automatic DNS/TLS activation).
- Logo supports upload + URL fallback in UX (backend persistence is URL-based).

## Workstreams

| Workstream | Status | Notes |
| --- | --- | --- |
| Slice 0 - Tracker Setup | Completed | Tracker initialized with required structure and dated header. |
| Slice 1 - Backend Model + API Surface | Completed | Model/migration/API surface + auth templates/users/domains endpoints shipped. |
| Slice 2 - Membership + Security Enforcement | Completed | Blocked membership enforcement + session revocation + principal rejection shipped. |
| Slice 3 - Frontend IA Refactor (Preview/Config) | Completed | Workspace IA migrated to `Preview | Config` with `Overview | Users | Domains | Code`. |
| Slice 4 - Runtime Auth UI Templating | Completed | Login/signup render by `auth_template_key` with branding fallback. |
| Tests + test_state updates | Completed | Backend and frontend feature suites updated and passing. |
| Documentation reconciliation | Completed | Core docs updated for new IA, domains request tracking, and auth templates. |

## Checkpoints
- 2026-02-15: Added `published_apps` fields in model: `description`, `logo_url`, `visibility`, `auth_template_key`.
- 2026-02-15: Added `published_app_custom_domains` model/table shape and enums.
- 2026-02-15: Added Alembic migration `b1c2d3e4f5a6_add_apps_config_visibility_and_domains.py`.
- 2026-02-15: Added auth template catalog service `published_app_auth_templates.py` and template manifests.
- 2026-02-15: Extended admin API in split modules (`routes_apps`, `routes_publish`) for new app fields, auth templates listing, users list/update, and domain request endpoints.
- 2026-02-15: Extended public config/runtime payloads with branding/auth-template/visibility and enforced visibility gate on published public endpoints.
- 2026-02-15: Added blocked membership enforcement in `published_app_auth_service` and `api/dependencies.py`.
- 2026-02-15: Refactored workspace UI to tabs `Preview | Config`, config sections `Overview | Users | Domains | Code`, and code-mode back-navigation.
- 2026-02-15: Added app creation auth-template selection and frontend service contracts for users/domains/config updates.
- 2026-02-15: Added runtime signup page auth-template rendering parity with login (`auth-classic`, `auth-split`, `auth-minimal` + fallback).
- 2026-02-15: Added backend tests for new fields/auth templates/users block/unblock/domain requests/visibility gating and blocked membership behavior.
- 2026-02-15: Added frontend tests for `Preview | Config` flows, overview/users/domains actions, and auth template rendering.

## Blockers / Open Items
- Custom app data collections/profile schema remains explicitly deferred to the next phase.
- Custom domain lifecycle in this phase is request-tracking only (no DNS/TLS activation automation).

## Test Log
- 2026-02-15 20:34 UTC: `cd backend && pytest -q tests/published_apps` -> PASS (43 passed).
- 2026-02-15 20:34 UTC: `cd frontend-reshet && npm test -- src/__tests__/published_apps --runInBand` -> PASS (5 suites, 17 tests).
