# Settings Hub Spec

Last Updated: 2026-04-14

This document is the canonical product/specification overview for the organization-backed settings hub.

For the browser sign-in, org/project context, organization creation, project creation, and invite workflow, see:

- `docs/product-specs/organization_and_project_workflow_spec.md`

## Purpose

`/admin/settings` is the focused settings hub for:
- integration credentials
- organization-scoped default pointers
- organization profile updates

It should not duplicate stats, audit, or broader organization/security management surfaces that already exist elsewhere.

## Current Scope

The settings hub currently covers:
- integration credentials CRUD
- credential usage inspection
- credential status inspection
- force-disconnect delete flow for linked resources
- organization-backed default pointers stored in organization settings

It links out to organization, project, members/invites, and security pages rather than embedding those management UIs directly.

## Current Credential Categories

- `llm_provider`
- `vector_store`
- `tool_provider`
- `custom`

## Current Default Settings

Currently stored on the organization record (`Tenant.settings` in the current implementation):
- `default_chat_model_id`
- `default_embedding_model_id`
- `default_retrieval_policy`

Current validation behavior:
- default chat model must resolve to an active chat model in organization/global scope
- default embedding model must resolve to an active embedding model in organization/global scope
- retrieval policy must be valid for the current enum

## Current API Surface

Credential APIs:
- `GET /admin/settings/credentials`
- `POST /admin/settings/credentials`
- `PATCH /admin/settings/credentials/{id}`
- `GET /admin/settings/credentials/{id}/usage`
- `DELETE /admin/settings/credentials/{id}`
- `GET /admin/settings/credentials/status`

Tenant profile/settings APIs:
- `PATCH /api/tenants/{tenant_slug}`
- `GET /api/tenants/{tenant_slug}/settings`
- `PATCH /api/tenants/{tenant_slug}/settings`

Current organization/project workflow APIs live separately under:

- `POST /auth/context/organization`
- `POST /auth/context/project`
- `GET /api/organizations`
- `POST /api/organizations`
- `GET /api/organizations/{organization_slug}/projects`

## Current Behavioral Rules

- credential values are not returned directly; only key names are exposed in response payloads
- unsupported provider keys are rejected by category
- deleting a credential with linked resources is blocked unless `force_disconnect=true`
- force-disconnect deletion clears linked credential references on model bindings and knowledge stores
- force-disconnect deletion also removes tool `implementation.credentials_ref` links so runtime falls back to platform defaults

## Runtime Resolution Rule

Current precedence is:
1. explicit `credentials_ref`
2. organization default credential
3. platform environment default

## Current Known Cleanup Boundary

The product model is now organization + project, but this settings surface still uses some `tenant` route shapes and model names internally.

That terminology is implementation debt, not the intended control-plane vocabulary.

## Canonical Implementation References

- `backend/app/api/routers/settings.py`
- `backend/app/api/routers/org_units.py`
- `backend/app/services/credentials_service.py`
- `backend/app/services/model_resolver.py`
- `backend/app/db/postgres/models/registry.py`
