# Settings Hub Spec (Tenant-Centric)

Last Updated: 2026-02-22

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
  - `tool_provider`
  - `custom`
- Credentials stay write-only.
- `Tools` is now a first-class credentials section (same list behavior as other provider categories).
- Provider selection behavior:
  - `llm_provider`: provider dropdown aligned with model registry provider list.
  - `vector_store`: provider dropdown (pinecone/qdrant/pgvector).
  - `tool_provider`: provider dropdown (`serper`, `tavily`, `exa`).
  - `custom`: free-form provider key input.
- Each credential supports `is_default` and default switching in-scope (tenant/category/provider[/variant]).

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
- Current shape:
  - `tenant_id` nullable (`null` remains schema-capable but platform defaults are env-managed in this phase)
  - `category`, `provider_key`, `provider_variant`
  - `credentials`, `is_enabled`, `is_default`

## Security Requirements
- Credentials are never returned as values (keys only).
- Tenant settings/profile mutation endpoints enforce owner/admin/global-admin permissions.
- Credential delete remains blocked when referenced by model bindings or knowledge stores.
- Integrations delete flow now exposes linked-resource usage and supports force-disconnect delete:
  - linked model providers and knowledge stores are switched to platform default (`credentials_ref = null`)
  - linked tools drop `implementation.credentials_ref` and then use platform default env keys at runtime

## API Surface
- Existing credentials APIs:
  - `GET /admin/settings/credentials`
  - `POST /admin/settings/credentials`
  - `PATCH /admin/settings/credentials/{id}`
  - `GET /admin/settings/credentials/{id}/usage`
  - `DELETE /admin/settings/credentials/{id}` (`force_disconnect=true` to detach linked resources)
  - `GET /admin/settings/credentials/status`
- New tenant settings/profile APIs:
  - `PATCH /api/tenants/{tenant_slug}`
  - `GET /api/tenants/{tenant_slug}/settings`
  - `PATCH /api/tenants/{tenant_slug}/settings`

## Notes
- Runtime precedence for provider credentials:
  1. Explicit `credentials_ref` on model/tool/store binding.
  2. Tenant default credential.
  3. Platform env default.
- Platform credentials are env-only in this phase (no startup seeding into `integration_credentials`).
- Activity/stats remain in dedicated stats/audit pages, not in settings hub.
