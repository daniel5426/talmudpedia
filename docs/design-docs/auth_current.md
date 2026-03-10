# Auth and Workload Security Current State

Last Updated: 2026-03-10

This document is the canonical current-state overview for authentication, authorization, and workload security in Talmudpedia.

## Purpose

The platform currently has three major auth surfaces:
- user/admin API auth
- delegated workload auth for internal runtime actions
- published-app runtime auth

These share platform security infrastructure, but they do not all use the same token type or principal model.

## Current Principal Types

### User principal

Used for normal internal/admin API traffic.

Current characteristics:
- bearer JWT
- tenant-scoped
- RBAC-derived scopes
- resolved by `get_current_principal()` through the user-token path

### Workload principal

Used for internal delegated runtime actions.

Current characteristics:
- short-lived delegated workload JWT
- validated against workload JWKS
- tied to a delegation grant and jti registry
- resolved by `get_current_principal()` through the workload-token path

### Published-app principal

Used for published runtime surfaces.

Current characteristics:
- app-scoped session token or preview token
- app-account-based identity
- separate from internal/admin bearer-token auth

## Current Authorization Model

The platform is now primarily scope-based.

Important current mechanisms:
- canonical scope catalog in `backend/app/core/scope_registry.py`
- `get_current_principal()`
- `require_scopes(...)`
- `ensure_sensitive_action_approved(...)`

This means route protection is no longer just role-name driven. The main control-plane and workload-protected routes use scope enforcement.

## Current User/Admin Auth

User/admin flows currently use:
- internal JWT bearer auth
- tenant context carried in token claims
- RBAC role assignments that resolve to scope keys

Current important behavior:
- secure endpoints do not rely on permissive tenant fallback
- tenant context is expected explicitly on migrated secure paths
- platform-admin style roles still act as a broad privileged override

## Current Workload Delegation Model

Delegated workload auth is the current model for internal runtime actions that need secured internal API access.

Current flow:
1. create or resolve a workload principal
2. create a delegation grant
3. compute effective scopes by least-privilege intersection
4. mint a short-lived workload token
5. validate jti and scopes at secured endpoints

Current internal endpoints:
- `POST /internal/auth/delegation-grants`
- `POST /internal/auth/workload-token`
- `GET /.well-known/jwks.json`

Current invariant:

`effective_scopes = user_scopes ∩ approved_workload_scopes ∩ requested_scopes`

Current security characteristics:
- agent principals must already be provisioned before runtime grant creation
- workload token usage is short-lived and jti-tracked
- sensitive workload mutations can require explicit approval decisions

## Current Published-App Auth

Published-app auth is a separate auth surface with its own principal model.

Current verified behavior:
- published-app auth resolves to app-local account principals
- session tokens include app and app-account claims
- thread ownership on published runtime surfaces is app-account scoped
- preview runtime uses preview-token principals
- a global `User` link may exist as a human correlation record, but it is not the authoritative published-app principal

This means published-app auth is now unified in backend control, while still being app-account scoped in runtime identity.

## Current Cross-Cutting Security Model

Security currently spans:
- token validation
- tenant scoping
- scope enforcement
- approval enforcement for sensitive workload actions
- audit/workload traceability
- published-app app-account/session isolation

The system should now be understood as having:
- one broad scope-based control-plane authorization model
- one delegated workload model for runtime-to-internal actions
- one separate published-app runtime auth model

## Canonical Implementation References

- `backend/app/api/dependencies.py`
- `backend/app/core/scope_registry.py`
- `backend/app/api/routers/internal_auth.py`
- `backend/app/api/routers/workload_security.py`
- `backend/app/services/delegation_service.py`
- `backend/app/services/token_broker_service.py`
- `backend/app/services/workload_identity_service.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/api/routers/published_apps_public.py`
- `backend/app/api/routers/published_apps_host_runtime.py`
