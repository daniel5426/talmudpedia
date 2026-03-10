# Settings Hub Spec

Last Updated: 2026-03-10

This document is the canonical product/specification overview for the tenant settings hub.

## Purpose

`/admin/settings` is the tenant-centric hub for:
- integration credentials
- tenant default pointers
- tenant profile updates

It should not duplicate stats, audit, or broader organization/security management surfaces that already exist elsewhere.

## Current Scope

The settings hub currently covers:
- integration credentials CRUD
- credential usage inspection
- credential status inspection
- force-disconnect delete flow for linked resources
- tenant default pointers stored in tenant settings

It links out to organization and security pages rather than embedding those management UIs directly.

## Current Credential Categories

- `llm_provider`
- `vector_store`
- `tool_provider`
- `custom`

## Current Default Settings

Stored in `Tenant.settings`:
- `default_chat_model_id`
- `default_embedding_model_id`
- `default_retrieval_policy`

Current validation behavior:
- default chat model must resolve to an active chat model in tenant/global scope
- default embedding model must resolve to an active embedding model in tenant/global scope
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

## Current Behavioral Rules

- credential values are not returned directly; only key names are exposed in response payloads
- unsupported provider keys are rejected by category
- deleting a credential with linked resources is blocked unless `force_disconnect=true`
- force-disconnect deletion clears linked credential references on model bindings and knowledge stores
- force-disconnect deletion also removes tool `implementation.credentials_ref` links so runtime falls back to platform defaults

## Runtime Resolution Rule

Current precedence is:
1. explicit `credentials_ref`
2. tenant default credential
3. platform environment default

## Canonical Implementation References

- `backend/app/api/routers/settings.py`
- `backend/app/api/routers/org_units.py`
- `backend/app/services/credentials_service.py`
- `backend/app/services/model_resolver.py`
- `backend/app/db/postgres/models/registry.py`
