# Published Apps Auth Gate and User Scope

Last Updated: 2026-03-09

## Purpose
This document describes the current published-app auth model as implemented in code:
- the unified auth gate shared by all published apps
- the current user/session/membership boundaries
- the current gap: published-app users are **not fully isolated per app**

## Short Answer
- Yes, published apps use a unified backend auth gate and shared host-runtime auth shell.
- Yes, published-app auth now resolves to an app-local account principal per app.
- Sessions and thread ownership are now scoped by published-app account.
- A global `users` record may still exist as an optional human link, but it is not the published-app authorization principal.

## Files Of Record
- `backend/app/api/routers/published_apps_host_runtime.py`
- `backend/app/api/routers/published_apps_public.py`
- `backend/app/api/dependencies.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/services/published_app_auth_shell_renderer.py`
- `backend/app/db/postgres/models/published_apps.py`
- `backend/app/db/postgres/models/identity.py`

## Unified Auth Gate
Published apps share one backend-controlled runtime/auth gate:
- App host requests are intercepted by `PublishedAppsHostRuntimeMiddleware`.
- If app auth is enabled and there is no valid app session cookie, the backend serves the centralized auth shell.
- The same host then serves the published runtime HTML once auth is satisfied.

Current host-gated auth/runtime endpoints live under:
- `/_talmudpedia/auth/state`
- `/_talmudpedia/auth/signup`
- `/_talmudpedia/auth/login`
- `/_talmudpedia/auth/exchange`
- `/_talmudpedia/auth/logout`

This means individual published apps do not each implement their own separate auth backend. They all flow through the same backend auth shell and host-runtime gateway.

## What Is App-Scoped Today
The following records are scoped per published app:
- `published_app_accounts`
- `published_app_sessions`
- `published_app_external_identities`
- published runtime principal resolution
- published runtime thread ownership

Current app-scoped protections in code:
- published session tokens include `app_id` and `app_account_id`
- session lookup verifies `session_id`, `app_id`, and `app_account_id`
- app account status is enforced per app
- thread access verifies `(published_app_id, app_account_id)` on published runtime surfaces

This is real isolation at the app-account/session/thread layer.

## What Is Still Shared Across Apps
An optional human correlation record can still exist globally through `users`.

Current password flow behavior:
- signup and login resolve against app-local credentials on `published_app_accounts`
- duplicate emails across apps are allowed
- a global `User` link may exist, but it is not required for app auth

Current Google flow behavior:
- Google resolves or creates an app-local account first
- a global `User` link may be attached for same-human correlation

Current external OIDC flow behavior:
- `PublishedAppExternalIdentity` is app-scoped by `(published_app_id, provider, issuer, subject)`
- it resolves to an app-local account
- it can additionally point to a global `users.id` as an optional human link

## Why Users Appear Shared Between Apps
The previous implementation shared users because app auth was layered on global `User`.
That is no longer the principal model.

The current model is:
- app-scoped account principal
- app-scoped sessions
- app-scoped thread ownership
- optional global human link

That means the same email/person can still exist across multiple apps, but as different app accounts with separate auth state and history ownership.

## Current Data Model
Implemented in `backend/app/db/postgres/models/published_apps.py`:

- `PublishedAppAccount`
  - unique on `(published_app_id, email)`
  - status is app-specific (`active` / `blocked`)
  - owns app-local credentials and profile state
- `PublishedAppSession`
  - belongs to `(published_app_id, app_account_id)`
  - token/session lifecycle is app-specific
- `PublishedAppExternalIdentity`
  - unique on `(published_app_id, provider, issuer, subject)`
  - links to `app_account_id`
  - can optionally link back to global `user_id`

Important implication:
- `PublishedAppAccount` is now the canonical published-app user object.
- There is now an app-local email namespace for password auth.

## Verified Code Paths
Verified against current code on 2026-03-09:

- Host runtime serves auth shell when cookie auth is missing:
  - `backend/app/api/routers/published_apps_host_runtime.py`
- Password signup/login uses app-local account lookup:
  - `backend/app/services/published_app_auth_service.py`
- Principal resolution requires app-scoped session + app account:
  - `backend/app/api/dependencies.py`
  - `backend/app/api/routers/published_apps_host_runtime.py`
- Published-app auth data model is app-account scoped, with optional global human links:
  - `backend/app/db/postgres/models/published_apps.py`
- Published runtime thread ownership is app-account scoped:
  - `backend/app/db/postgres/models/agent_threads.py`
  - `backend/app/services/thread_service.py`

## Doc Reconciliation
Older broad docs were directionally correct about the unified auth gate, but were outdated on the principal model.

Current accurate wording is:
- Published apps share a unified backend auth gate.
- Published app sessions and thread ownership are app-account scoped.
- Published app users are now backed by `published_app_accounts`.
- Global `users` can still be used as optional human links, but they are not authoritative for published-app auth or history ownership.
