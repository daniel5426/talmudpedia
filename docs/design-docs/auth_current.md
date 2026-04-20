# Auth Current State

Last Updated: 2026-04-19

This document is the canonical current-state auth and authorization overview.

For the browser signup/sign-in/org/project workflow, see:

- `docs/product-specs/organization_and_project_workflow_spec.md`

## Current Auth Surfaces

- browser control-plane auth
- user/admin API auth
- published-app runtime auth
- embedded/public runtime auth

The delegated workload-auth system has been removed.

## Browser Control-Plane Auth

Browser auth now uses WorkOS AuthKit with a sealed WorkOS session cookie plus a local project-context cookie.

The active browser session carries:

- authenticated user identity from WorkOS
- active organization from WorkOS
- active project from Talmudpedia

Browser control-plane requests are expected to resolve auth and active context from the server session, not from:

- local-storage bearer tokens
- Google ID tokens posted directly to the platform
- local password auth as the browser source of truth

Current browser auth endpoints:

- `GET|POST /auth/login`
- `GET|POST /auth/signup`
- `GET|POST /auth/register`
- `GET /auth/callback`
- `GET /auth/session`
- `POST /auth/logout`
- `POST /auth/context/organization`
- `POST /auth/context/project`

## Current Authorization Model

- WorkOS remains the browser identity and session source.
- Local Talmudpedia roles are the control-plane authorization source of truth.
- Organization-scoped and project-scoped effective permissions are resolved locally from role assignments.
- resource policy sets remain the runtime-facing access and quota layer
- `platform-architect` is the only special internal case and uses architect modes:
  - `read_only`
  - `default`
  - `full_access`

## Current Runtime Security Model

- normal agent/tool/model/knowledge-store access is enforced through resource-policy snapshots
- snapshots resolve once at run start and are re-checked at each protected resource boundary
- published-app and embedded runtimes resolve their own principal type into resource-policy assignment/default-policy resolution
- `platform-architect` no longer uses workload principals, grants, or workload JWTs
- `platform-architect` runs with a requested architect mode capped by the caller’s maximum allowed mode

## Current Programmatic Auth Boundary

The browser and programmatic auth paths are intentionally separate.

- browser control-plane access uses the WorkOS session cookie model
- `POST /auth/token` remains temporary compatibility for explicit bearer flows
- machine/runtime credentials should be scoped to the owning resource model rather than treated as browser login tokens

## Current Bridge Boundary

- Published-app auth still uses the app-local auth/session bridge.
- Control-plane auth no longer shares the browser-session implementation with published apps.

## Canonical Implementation References

- `backend/app/api/routers/auth.py`
- `backend/app/api/dependencies.py`
- `backend/app/services/workos_auth_service.py`
- `backend/app/services/auth_context_service.py`
- `backend/app/services/organization_bootstrap_service.py`
- `backend/app/api/routers/organizations.py`
- `backend/app/api/routers/workos_webhooks.py`
- `backend/app/core/scope_registry.py`
- `backend/app/api/routers/resource_policies.py`
- `backend/app/services/resource_policy_service.py`
- `backend/app/services/resource_policy_quota_service.py`
- `backend/app/services/architect_mode_service.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/api/routers/published_apps_host_runtime.py`
