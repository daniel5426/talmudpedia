# Authentication Overview

Last Updated: 2026-02-08

This document describes authentication types currently used by the platform.

## Auth Types at a Glance

| Auth Type | Token/Mechanism | Issuer | Where Used | Lifetime |
| --- | --- | --- | --- | --- |
| User Access Token | JWT (Bearer) | `/auth/login`, `/auth/register`, `/auth/google` | User-facing APIs | ~90 days |
| Delegated Workload Token | JWT (Bearer, asymmetric) | `/internal/auth/workload-token` | Internal workload -> internal API | ~5 minutes |
| Google SSO | Google ID token -> platform JWT | `/auth/google` | Browser login | External + platform TTL |

## 1) User Access Tokens
- Signed with `SECRET_KEY`.
- Claims include `sub`, `tenant_id`, `org_role`, `exp`.
- Used for normal user and admin API traffic.

## 2) Delegated Workload Tokens
- Signed with workload key material (JWKS published at `/.well-known/jwks.json`).
- Issued only after delegation grant creation.
- Claims include workload identity, grant identity, tenant, scope, and jti.
- Used for internal service-to-service runtime actions.

## 3) Delegation Grants
- Created by `/internal/auth/delegation-grants`.
- Effective scopes are least-privilege intersection of user, approved workload policy, and requested scopes.
- Grants are revocable and expire.

## 4) Scope Enforcement
Secure endpoints enforce scopes via principal dependency + `require_scopes(...)`.
Current migrated write/read paths include Group A, B, and C endpoint groups:
- Group A: catalog + create routes for pipelines/agents/tools/artifacts.
- Group B: mutation routes (`PUT/DELETE/publish/promote/version/compile`) for agents/tools/artifacts/pipelines.
- Group C: agent run/test/execute routes (`execute`, `stream`, `run`, `resume`, `validate`).

Sensitive mutation routes additionally require explicit approval decisions for workload principals.

## 5) Tenant Context
- Secure workload flows require tenant context from signed token claims.
- Fallback tenant inference is not used on migrated secure endpoints.

## 6) Governance
Tenant admins can review and approve/reject workload scope policies via workload security admin endpoints.

## Common Failures
- `401 Unauthorized`: token missing/invalid/revoked/jti inactive.
- `403 Forbidden`: token valid but required scope missing.
- `403 Forbidden (Sensitive action requires explicit approval)`: workload token has scope but approval decision is missing.
- `Tenant context required`: no valid tenant context in principal.

## Legacy Paths
- Legacy service-token decode fallback is removed from secure dependencies.
- Env-based privileged internal auth fallback is removed from Platform SDK artifact flow.
