# WorkOS Migration Architecture

Last Updated: 2026-04-19

This document is the canonical current-state reference for the staged WorkOS migration.

## What Is Live

- The control-plane browser auth flow now redirects into WorkOS AuthKit.
- The backend callback stores a sealed WorkOS session cookie.
- Local records map WorkOS identifiers into:
  - `users.workos_user_id`
  - `tenants.workos_organization_id`
  - `org_memberships.workos_membership_id`
- The active project remains local to Talmudpedia and is tracked separately from the WorkOS session.

## Split Responsibilities

- WorkOS owns:
  - user authentication
  - browser session lifecycle
  - organization identity
  - organization membership identity
  - hosted sign-in and sign-up UX
- Talmudpedia owns:
  - `Project`
  - project-scoped RBAC
  - resource policies and quotas
  - runtime authorization
  - published-app bridge auth

## Current Bridge Boundaries

- Published apps still use their app-local auth/session system.
- Programmatic bearer tokens from `POST /auth/token` remain temporary compatibility only.
- Local org-level RBAC remains as fallback when WorkOS permissions are not yet configured for a session.

## Key Implementation Files

- `backend/app/services/workos_auth_service.py`
- `backend/app/api/routers/auth.py`
- `backend/app/api/routers/workos_webhooks.py`
- `backend/app/api/dependencies.py`

## Follow-up Work

- Move organization invitations fully onto WorkOS invitations.
- Add event-specific WorkOS webhook reconciliation beyond idempotent storage.
- Migrate published-app auth from local credentials to WorkOS-backed app-isolated identities.
