# Settings Hub Spec (Tenant-Centric)

Last Updated: 2026-02-15

## Purpose
Define `/admin/settings` as a tenant-centric hub for real settings, without duplicating analytics or activity surfaces that already exist elsewhere.

## Scope
- Tenant profile management (name, slug, status).
- Tenant default pointers (chat model, embedding model, retrieval policy) stored in `Tenant.settings`.
- Existing credentials CRUD (integrations) remains in settings.
- Security and Organization are linked modules, not duplicated UIs.

## UI Sections
### 1. Tenant Profile
- Editable: `name`, `slug`, `status`.
- Slug-change warning shown in UI.
- Mutations restricted to tenant owner/admin and global admin.

### 2. Integrations
- Existing credential categories:
  - `llm_provider`
  - `vector_store`
  - `artifact_secret`
  - `custom`
- Credentials stay write-only.
- Includes a dedicated simplified Web Search setup card:
  - `Serper API Key` single input (no manual JSON required in UX)
  - Persists to integration credentials as:
    - `category=custom`
    - `provider_key=web_search`
    - `provider_variant=serper`
    - `credentials.api_key=<value>`
  - If present and enabled, this tenant key overrides platform default web-search key.
  - If tenant key is not set, runtime falls back to platform-level `SERPER_API_KEY`.

### 3. Defaults
- `default_chat_model_id`
- `default_embedding_model_id`
- `default_retrieval_policy`
- Validation:
  - Chat default must resolve to active chat model in tenant/global scope.
  - Embedding default must resolve to active embedding model in tenant/global scope.
  - Retrieval policy must be enum-valid.

### 4. Security & Organization
- Link cards only to existing pages:
  - `/admin/organization`
  - `/admin/security`
- No embedded management duplication in settings.

## Data Model Mapping
### Tenant
- `tenants.settings` (JSONB) keys used by settings hub:
  - `default_chat_model_id`
  - `default_embedding_model_id`
  - `default_retrieval_policy`

### IntegrationCredential
- Unchanged:
  - `category`, `provider_key`, `provider_variant`, `credentials`, `is_enabled`.

## Security Requirements
- Credentials are never returned as values (keys only).
- Tenant settings/profile mutation endpoints enforce owner/admin/global-admin permissions.
- Credential delete remains blocked when referenced by model bindings or knowledge stores.

## API Surface
- Existing credentials APIs:
  - `GET /admin/settings/credentials`
  - `POST /admin/settings/credentials`
  - `PATCH /admin/settings/credentials/{id}`
  - `DELETE /admin/settings/credentials/{id}`
  - `GET /admin/settings/credentials/status`
- New tenant settings/profile APIs:
  - `PATCH /api/tenants/{tenant_slug}`
  - `GET /api/tenants/{tenant_slug}/settings`
  - `PATCH /api/tenants/{tenant_slug}/settings`

## Notes
- No DB migration required for v1; defaults are new keys in existing JSONB.
- Activity/stats remain in dedicated stats/audit pages, not in settings hub.
