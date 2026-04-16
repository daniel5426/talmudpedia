# Published Apps Spec

Last Updated: 2026-04-16

This document is the canonical product/specification overview for published apps.

Published apps are distinct from the embedded-agent runtime product. If a customer only wants to call a published agent from its own existing application, that flow now belongs to `docs/product-specs/embedded_agent_runtime_spec.md` and does not require creating a published app.

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
- app analytics for admin list/detail surfaces
- published-app runtime routes
- builder preview and draft-development flows
- published and draft revision pointers
- app-scoped auth with selectable auth templates
- custom domain request tracking
- persisted authenticated chat behavior for published runtime

Current repo state note:
- the previous published-app UI template packs were removed from source control
- template infrastructure and `template_key` fields still exist in the implementation
- there is now one active checked-in starter template pack at `backend/app/templates/published_apps/classic-chat/`
- the canonical template key is `classic-chat`

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
- Runtime chat surfaces support upload-first attachments for `image`, `document`, and `audio`.
- Saved draft versions are always durable, watcher-materialized revisions.
- Publish is pointer-only against an already materialized revision and fails with `REVISION_NOT_MATERIALIZED` when durable dist is missing.

## Current Runtime Surface

The current backend exposes these main published-app surfaces:
- admin management and builder APIs under `/admin/apps`
- app analytics APIs under `/admin/apps/stats` and `/admin/apps/{app_id}/stats`
- preview runtime and discovery endpoints under `/public/apps`
- external runtime/auth/history endpoints under `/public/external/apps`
- hosted runtime/internal auth surface in `published_apps_host_runtime`
- builder preview proxy/runtime flows for draft development and preview assets

Notable current public/runtime routes include:
- `/public/apps/{app_slug}/config`
- `/public/external/apps/{app_slug}/runtime/bootstrap`
- `/public/external/apps/{app_slug}/attachments/upload`
- `/public/external/apps/{app_slug}/chat/stream`
- `/public/external/apps/{app_slug}/auth/*`
- `/public/external/apps/{app_slug}/threads`
- `/public/apps/preview/revisions/{revision_id}/runtime`
- `/public/apps/preview/revisions/{revision_id}/runtime/bootstrap`
- `/public/apps/preview/revisions/{revision_id}/attachments/upload`
- `/public/apps/preview/revisions/{revision_id}/chat/stream`
- `/_talmudpedia/attachments/upload`

Important current behavior verified in code:
- source-UI mode has been removed
- `/public/apps/{slug}/ui` returns `410 UI_SOURCE_MODE_REMOVED`
- legacy path-mode published runtime/auth/chat endpoints under `/public/apps/{slug}/*` remain hard-cut and return `410`
- externally hosted clients should use the dedicated `/public/external/apps/{slug}/*` runtime/auth/history surface
- preview source-UI mode is also removed in favor of runtime/bootstrap flows
- runtime attachments are upload-first and chat requests reference `attachment_ids`
- thread detail payloads include attachment descriptors so replay preserves file context
- host and external thread detail endpoints also support optional nested subagent thread trees via `include_subthreads=true`
- nested thread payloads expose `lineage` plus recursive `subthread_tree` nodes with `thread`, `turns`, `paging`, `has_children`, and `children`
- runtime bootstrap records app bootstrap-view and visit-start analytics events
- app analytics exclude preview bootstrap traffic by default and exclude builder coding-agent runs from runtime usage totals

## Data Model Shape

Current app-related persistence includes:
- published apps
- analytics events
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
- external runtime is bearer/CORS oriented; host runtime is cookie/host-shell oriented

## Canonical Implementation References

- `backend/app/api/routers/published_apps_admin.py`
- `backend/app/api/routers/published_apps_public.py`
- `backend/app/api/routers/published_apps_host_runtime.py`
- `backend/app/api/routers/published_apps_builder_preview_proxy.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/services/published_app_templates.py`
- `backend/app/services/published_app_auth_templates.py`
- `backend/app/db/postgres/models/published_apps.py`
