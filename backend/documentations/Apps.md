# Apps Feature (Published Client Web Apps)

Last Updated: 2026-02-11

## Purpose
`Apps` lets each tenant publish a production app bound to one of their published agents, with a builder flow for custom UI templates, revisions, and published snapshots.

## Product Scope (Current)
- Add an admin control plane under `/admin/apps` to create/manage apps.
- Provide a builder workspace (`Preview | Code`) with template-based draft creation.
- Serve published runtime from immutable published revisions.
- Support app-level auth with default ON behavior.
- Include auth providers: email/password and Google.
- Exclude subscriptions/billing and custom domains in these phases.

## Core Behavior
- Every app belongs to a tenant and references one published agent.
- Runtime URL pattern is subdomain-based (`{appSlug}.apps.{platform-domain}`), with `/published/[appSlug]` support for local/dev.
- Auth is enabled by default when creating an app.
- App owners can disable auth per app.
- When auth is enabled, chat history is persisted and scoped by `published_app_id` + user.
- When auth is disabled, runtime supports public ephemeral chat mode (non-persistent in v1).
- App create now accepts `template_key`; `slug` is optional and auto-generated if omitted.
- `chat-grid` now maps to a premium multi-file LayoutShell-style workspace template (sidebar + chat + source list + resizable source viewer + mobile overlays) with generic placeholder source data.
- Each app tracks both current draft and current published revision pointers.
- Template switch is destructive for draft state and requires explicit confirmation in the UI.

## Backend Architecture
- Admin API router: `backend/app/api/routers/published_apps_admin.py`
  - CRUD + templates + builder state/revision/template-reset + builder SSE + conversation replay + revision build status/retry + publish snapshot.
- Public runtime API router: `backend/app/api/routers/published_apps_public.py`
  - host resolve, runtime config, runtime descriptors, auth flows, chat runtime endpoints, published UI snapshot endpoints, and preview asset proxy endpoints.
- Auth domain service: `backend/app/services/published_app_auth_service.py`
  - signup/login, memberships, session issuance/revocation, OAuth callbacks.
- Template service: `backend/app/services/published_app_templates.py`
  - filesystem-backed template pack loading from `backend/app/templates/published_apps/{template_key}/`.
- Dependency governance: `backend/app/services/apps_builder_dependency_policy.py`
  - curated semi-open package policy with pinned versions and import/declaration validation.
- Bundle storage service: `backend/app/services/published_app_bundle_storage.py`
  - S3-compatible dist artifact copy/read operations for publish promotion and preview asset proxy streaming.
- Principal dependencies include published-app session validation in:
  - `backend/app/api/dependencies.py`
  - includes preview-token principal for builder preview UI endpoints.

## Data Model
- `published_apps`
  - app identity, tenant ownership, connected `agent_id`, auth settings, publish status/url, `template_key`, and draft/published revision pointers.
- `published_app_revisions`
  - immutable revision records for draft/published states, full Vite project files map, entry file, build lifecycle (`build_status`, `build_seq`, timestamps/errors), dist metadata (`dist_storage_prefix`, `dist_manifest`), source lineage.
- `published_app_user_memberships`
  - user-to-app access relation and login status metadata.
- `published_app_sessions`
  - session/token lifecycle tracking (`jti`, expiry, revocation).
- `chats` extension
  - nullable `published_app_id` for persisted app-scoped chat history.

Migration:
- `backend/alembic/versions/9a4c7e21b3d5_add_published_apps_phase1_3.py`
- `backend/alembic/versions/c4d5e6f7a8b9_add_published_app_revisions_builder_v1.py`
- `backend/alembic/versions/d2e3f4a5b6c7_add_builder_conversation_turns.py`
- `backend/alembic/versions/e3f4a5b6c7d8_add_published_app_revision_build_fields.py`

## Frontend Architecture
- Admin pages:
  - `frontend-reshet/src/app/admin/apps/page.tsx`
  - `frontend-reshet/src/app/admin/apps/[id]/page.tsx`
- Runtime pages:
  - `frontend-reshet/src/app/published/[appSlug]/page.tsx`
  - `frontend-reshet/src/app/published/[appSlug]/login/page.tsx`
  - `frontend-reshet/src/app/published/[appSlug]/signup/page.tsx`
  - `frontend-reshet/src/app/published/[appSlug]/auth/callback/page.tsx`
- Middleware host rewrite:
  - `frontend-reshet/src/middleware.ts`
- Services (single source of truth in `src/services/`):
  - `frontend-reshet/src/services/published-apps.ts`
  - `frontend-reshet/src/services/published-runtime.ts`
- Shared selector used for published-agent picking:
  - `frontend-reshet/src/components/shared/SearchableResourceInput.tsx`
- Builder feature module:
  - `frontend-reshet/src/features/apps-builder/`
  - includes `workspace/`, `preview/`, `editor/`, `state/`, `templates/`, `runtime-sdk/`

## Security and Isolation
- App runtime session tokens are separate from internal admin/workload flows.
- Cross-app access is prevented by filtering all app runtime reads/writes with app scope.
- Membership model enforces which users can access authenticated app data.
- Builder preview uses short-lived preview tokens and revision/app/tenant claims.
- Public UI endpoint serves published snapshot only (never draft); when `APPS_RUNTIME_MODE=static`, `/public/apps/{slug}/ui` returns `410 UI_SOURCE_MODE_REMOVED`.
- Publish artifact promotion copies built dist assets from draft revision prefix to published revision prefix; copy failures return `500 BUILD_ARTIFACT_COPY_FAILED` and leave app publish pointer unchanged.

## Current Constraints
- No billing/subscriptions yet.
- No custom domain mapping yet.
- Password policy baseline is currently minimal (v1).
- Builder chat patching is v1-level and intentionally permissive for UI usability (platform safety remains enforced on backend boundaries).

## Operational Notes
- If runtime/admin endpoints fail with missing `published_apps` relation, DB migrations are not fully applied.
- Required action: run Alembic to head in the backend environment used by the API process.
