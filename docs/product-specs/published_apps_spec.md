# Published Apps Spec

Last Updated: 2026-03-10

This document is the canonical product/specification overview for published apps.

## Purpose

Published apps let a tenant expose an agent-backed app experience with:
- admin-side app management
- builder and preview workflows
- published runtime delivery
- app-scoped auth and user/session behavior
- revisioned app content and publish flows

## Current Scope

The current product includes:
- admin control plane under `/admin/apps`
- app creation and management tied to tenant ownership
- published-app runtime routes
- builder preview and draft-development flows
- published and draft revision pointers
- app-scoped auth with selectable auth templates
- custom domain request tracking
- persisted authenticated chat behavior for published runtime

The current product does not yet include:
- billing/subscriptions
- automated DNS/TLS activation for custom domains
- generalized custom app data collections/profile schema

## Current Behavioral Contract

- Each app belongs to a tenant.
- Each app points to one published agent.
- Auth is enabled by default at app creation time.
- App visibility can be public or private.
- Published authenticated runtime supports persisted app-scoped chat behavior.
- Auth-disabled runtime supports public ephemeral chat behavior.
- Preview runtime supports real agent streaming, but preview chat execution is intentionally ephemeral.
- Version publish is build-aware and asynchronous when build artifacts are missing.
- If build-wait publish fails, the published pointer remains on the previously working revision.

## Current Runtime Surface

The current backend exposes these main published-app surfaces:
- admin management and builder APIs under `/admin/apps`
- public runtime and auth endpoints under `/public/apps`
- hosted runtime/internal auth surface in `published_apps_host_runtime`
- builder preview proxy/runtime flows for draft development and preview assets

Notable current public/runtime routes include:
- `/public/apps/{app_slug}/config`
- `/public/apps/{app_slug}/runtime`
- `/public/apps/{app_slug}/runtime/bootstrap`
- `/public/apps/{app_slug}/chat/stream`
- `/public/apps/{app_slug}/auth/*`
- `/public/apps/preview/revisions/{revision_id}/runtime`
- `/public/apps/preview/revisions/{revision_id}/runtime/bootstrap`
- `/public/apps/preview/revisions/{revision_id}/chat/stream`

Important current behavior verified in code:
- source-UI mode has been removed
- `/public/apps/{slug}/ui` returns `410 UI_SOURCE_MODE_REMOVED`
- preview source-UI mode is also removed in favor of runtime/bootstrap flows

## Data Model Shape

Current app-related persistence includes:
- published apps
- immutable revisions
- user memberships
- app accounts
- app sessions
- external identities
- custom domains
- coding chat sessions/messages
- draft workspaces and draft-dev sessions
- publish jobs

Published apps also integrate with agent threads and chat history through app-scoped relationships.

## Security and Isolation

- runtime session tokens are separate from internal/admin/workload auth flows
- runtime reads and writes are filtered by app scope
- preview runtime uses preview principals/tokens
- app membership and account/session state enforce access for authenticated apps

## Canonical Implementation References

- `backend/app/api/routers/published_apps_admin.py`
- `backend/app/api/routers/published_apps_public.py`
- `backend/app/api/routers/published_apps_host_runtime.py`
- `backend/app/api/routers/published_apps_builder_preview_proxy.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/services/published_app_templates.py`
- `backend/app/services/published_app_auth_templates.py`
- `backend/app/db/postgres/models/published_apps.py`
