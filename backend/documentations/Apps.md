# Apps Feature (Published Client Web Apps)

Last Updated: 2026-02-10

## Purpose
`Apps` lets each tenant publish a production web chat app that is bound to one of their published agents, without requiring the tenant to build their own frontend.

## Product Scope (Phases 1-3)
- Add an admin control plane under `/admin/apps` to create/manage apps.
- Serve a constant runtime chat template for end users.
- Support app-level auth with default ON behavior.
- Include auth providers: email/password and Google.
- Exclude subscriptions/billing and custom domains in these phases.
- Exclude template customization in these phases.

## Core Behavior
- Every app belongs to a tenant and references one published agent.
- Runtime URL pattern is subdomain-based (`{appSlug}.apps.{platform-domain}`), with `/published/[appSlug]` support for local/dev.
- Auth is enabled by default when creating an app.
- App owners can disable auth per app.
- When auth is enabled, chat history is persisted and scoped by `published_app_id` + user.
- When auth is disabled, runtime supports public ephemeral chat mode (non-persistent in v1).

## Backend Architecture
- Admin API router: `backend/app/api/routers/published_apps_admin.py`
  - CRUD + publish/unpublish + runtime preview endpoints.
- Public runtime API router: `backend/app/api/routers/published_apps_public.py`
  - host resolve, runtime config, auth flows, and chat runtime endpoints.
- Auth domain service: `backend/app/services/published_app_auth_service.py`
  - signup/login, memberships, session issuance/revocation, OAuth callbacks.
- Principal dependencies include published-app session validation in:
  - `backend/app/api/dependencies.py`

## Data Model
- `published_apps`
  - app identity, tenant ownership, connected `agent_id`, auth settings, publish status/url.
- `published_app_user_memberships`
  - user-to-app access relation and login status metadata.
- `published_app_sessions`
  - session/token lifecycle tracking (`jti`, expiry, revocation).
- `chats` extension
  - nullable `published_app_id` for persisted app-scoped chat history.

Migration:
- `backend/alembic/versions/9a4c7e21b3d5_add_published_apps_phase1_3.py`

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

## Security and Isolation
- App runtime session tokens are separate from internal admin/workload flows.
- Cross-app access is prevented by filtering all app runtime reads/writes with app scope.
- Membership model enforces which users can access authenticated app data.

## Current Constraints
- No billing/subscriptions yet.
- No custom domain mapping yet.
- No template customization yet.
- Password policy baseline is currently minimal (v1).

## Operational Notes
- If runtime/admin endpoints fail with missing `published_apps` relation, DB migrations are not fully applied.
- Required action: run Alembic to head in the backend environment used by the API process.
