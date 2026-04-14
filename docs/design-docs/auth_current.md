# Auth Current State

Last Updated: 2026-04-14

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

Browser auth now uses secure HTTP-only cookie sessions.

The active browser session carries:

- authenticated user identity
- active organization
- active project

Browser control-plane requests are expected to resolve auth and active context from the server session, not from:

- local-storage bearer tokens
- token-embedded tenant claims as the browser source of truth
- first-membership inference after a session is established

Current browser auth endpoints:

- `POST /auth/signup`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/google`
- `GET /auth/session`
- `POST /auth/logout`
- `POST /auth/context/organization`
- `POST /auth/context/project`

## Current Authorization Model

- RBAC scopes remain the control-plane authorization model.
- scopes are split across organization scope and project scope
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

- browser control-plane access should use the session cookie model
- non-browser flows may still use bearer-style auth where explicitly implemented
- machine/runtime credentials should be scoped to the owning resource model rather than treated as browser login tokens

## Current Known Cleanup Boundary

Some backend and API naming still uses `tenant` at the implementation level even though the intended browser/control-plane model is organization + project.

That remaining terminology is cleanup debt, not the target product model.

## Canonical Implementation References

- `backend/app/api/routers/auth.py`
- `backend/app/api/dependencies.py`
- `backend/app/core/scope_registry.py`
- `backend/app/services/browser_session_service.py`
- `backend/app/services/auth_context_service.py`
- `backend/app/services/organization_bootstrap_service.py`
- `backend/app/api/routers/organizations.py`
- `backend/app/api/routers/resource_policies.py`
- `backend/app/services/resource_policy_service.py`
- `backend/app/services/resource_policy_quota_service.py`
- `backend/app/services/architect_mode_service.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/api/routers/published_apps_host_runtime.py`
