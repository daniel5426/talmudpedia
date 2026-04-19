# Authentication Overview

Last Updated: 2026-04-19

This document describes the current staged authentication model.

For navigation and reading order, see `backend/documentations/auth/00_auth_docs_guide.md`.

## Auth Types at a Glance

| Auth Type | Token/Mechanism | Issuer | Where Used | Lifetime |
| --- | --- | --- | --- | --- |
| Browser Session | WorkOS sealed session cookie + local project cookie | WorkOS AuthKit + platform callback | Control-plane browser auth | Managed by WorkOS session lifecycle |
| Programmatic User Token | JWT (Bearer) | `POST /auth/token` | Explicit non-browser compatibility flows | Platform JWT TTL |
| Published App Session | JWT (Bearer) | Published-app auth bridge | Published-app runtime auth | Published-app session TTL |

## 1) Browser Session
- Browser login and signup redirect into hosted WorkOS AuthKit.
- `GET /auth/callback` exchanges the authorization code and stores the sealed WorkOS session cookie.
- Organization context comes from the WorkOS session.
- Project context stays local in a separate cookie because `Project` is not modeled in WorkOS.

## 2) Programmatic User Tokens
- `POST /auth/token` is temporary compatibility for explicit bearer flows.
- Tokens are still signed with `SECRET_KEY`.
- Claims include `sub`, `tenant_id`, `project_id`, and `scope`.
- This path is no longer the browser login path.

## 3) Published App Sessions
- Published apps still use the app-local bridge during the WorkOS control-plane migration.
- Published-app session tokens remain separate from the control-plane browser session.

## 4) Scope Enforcement
- Secure endpoints enforce scopes via principal dependency + `require_scopes(...)`.
- Organization-level permissions come from WorkOS session permissions when present.
- Project-level permissions still come from local RBAC assignments.
- Sensitive mutation routes still rely on the shared principal + approval model already in place.

## 5) Organization Context
- Browser organization context is resolved from the authenticated WorkOS session.
- Project context is resolved locally and can be switched without mutating WorkOS state.
- Header-based tenant overrides remain explicit and separate.

## 6) Governance
- WorkOS is now the control-plane source for user identity, org identity, and browser session lifecycle.
- Local policy still owns resource policies, quotas, and runtime authorization.

## Common Failures
- `401 Unauthorized`: session missing, invalid, expired, or bearer token invalid.
- `403 Forbidden`: token/session valid but required scope missing.
- `400 Active organization context is required`: organization context missing on a tenant-scoped route.

## Legacy Paths
- `/auth/google` is no longer part of the control-plane browser flow.
- Local password/browser-session control-plane auth is no longer the canonical browser path.
- Published-app auth remains on the bridge until its own migration phase.
