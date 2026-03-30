# Auth Current State

Last Updated: 2026-03-30

This document replaces the old workload-security description.

## Current Auth Surfaces

- user/admin API auth
- published-app runtime auth
- embedded/public runtime auth

The delegated workload-auth system has been removed.

## Current Authorization Model

- RBAC scopes remain the control-plane authorization model.
- Resource policy sets are the tenant-facing access and quota layer.
- `platform-architect` is the only special internal case and uses architect modes:
  - `read_only`
  - `default`
  - `full_access`

## Runtime Security Model

- Normal agent/tool/model/knowledge-store access is enforced through resource-policy snapshots.
- Snapshots resolve once at run start and are re-checked at each protected resource boundary.
- Published-app and embedded runtimes resolve their own principal type into resource-policy assignment/default-policy resolution.
- `platform-architect` no longer uses workload principals, grants, or workload JWTs. It runs with a requested architect mode capped by the caller’s maximum allowed mode.

## Canonical Implementation References

- `backend/app/api/dependencies.py`
- `backend/app/core/scope_registry.py`
- `backend/app/api/routers/resource_policies.py`
- `backend/app/services/resource_policy_service.py`
- `backend/app/services/resource_policy_quota_service.py`
- `backend/app/services/architect_mode_service.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/api/routers/published_apps_public.py`
- `backend/app/api/routers/published_apps_host_runtime.py`
