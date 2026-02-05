# Authentication Overview

This document describes **all authentication types** supported by the platform today, how they are issued, and where they are accepted.

For identity and authorization model details, see `backend/documentations/authentication_v2.md`.

---

## Auth Types at a Glance

| Auth Type | Token/Mechanism | Issuer | Where Used | Lifetime |
| --- | --- | --- | --- | --- |
| User Access Token | JWT (Bearer) | `/auth/login`, `/auth/register`, `/auth/google` | Most API routes | 90 days |
| Google SSO | Google ID token -> JWT | `/auth/google` | Browser login | External (Google), then 90 days |
| Service Token | JWT (Bearer) | `create_service_token` | Internal SDK calls | 5 minutes |
| API Key Token | JWT (Bearer) stored in env | Set by ops | SDK client / internal tooling | Depends on token |

---

## 1) User Access Tokens (JWT)

**How it works**
- Users authenticate via email/password or Google SSO.
- The backend issues a JWT signed with `SECRET_KEY` (HS256).
- The token is sent as `Authorization: Bearer <token>`.

**Claims**
- `sub`: user UUID
- `tenant_id`: primary tenant context
- `org_unit_id`: org unit context
- `org_role`: membership role
- `exp`: expiration time

**Endpoints**
- `POST /auth/login`
- `POST /auth/register`
- `POST /auth/google`
- `GET /auth/me`

**Usage**
```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8000/auth/me
```

---

## 2) Google SSO

**How it works**
- The client obtains a Google ID token.
- The backend verifies it and issues a platform JWT.

**Endpoint**
- `POST /auth/google`

---

## 3) Service Tokens (New)

**Purpose**
Service tokens enable **internal service-to-service** calls that require admin-level access without exposing user credentials.

**Issuer**
- `create_service_token(tenant_id)` in `backend/app/core/internal_token.py`
- Signed with `PLATFORM_SERVICE_SECRET`

**Claims**
- `role = "platform-service"`
- `tenant_id = <uuid>`
- `exp = now + 5 minutes`

**Accepted Endpoints**
- `GET /admin/pipelines/catalog`
- `POST /admin/pipelines/visual-pipelines`
- `POST /agents`

---

## 4) API Key Tokens (Environment)

Some internal tools (including the SDK client) can use a token stored in environment variables:
- `PLATFORM_API_KEY`
- `API_KEY`

These are expected to be **valid JWTs** signed with `SECRET_KEY`.

---

## 5) Tenant Context Resolution

Tenant scope is resolved in two ways:
- From JWT claims (`tenant_id`)
- From headers when needed (`X-Tenant-ID`)

For admin endpoints, tenant scope is required unless the user is a system admin. Service tokens must always provide a tenant context.

---

## 6) Authorization Model (High-Level)

Authorization is handled by:
- `User.role` (system-level)
- `OrgMembership.role` (tenant-level)

Admins can access global data; tenant owners/admins are scoped to their tenant. See `authentication_v2.md` for details.

---

## Environment Variables

**Required**
- `SECRET_KEY` (JWT signing for user tokens)
- `PLATFORM_SERVICE_SECRET` (JWT signing for service tokens)

**Optional**
- `PLATFORM_API_KEY`
- `API_KEY`

---

## Common Failures

- `401 Unauthorized`: missing or invalid bearer token
- `403 Forbidden`: valid token but insufficient permissions
- `Tenant context required`: token missing tenant scope
