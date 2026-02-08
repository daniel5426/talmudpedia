# Settings Page Spec (Credentials & Integrations)

Last Updated: 2026-02-05

## Purpose
Define a tenant-scoped Settings page for managing external integration credentials, including LLM providers, vector stores, and artifact secrets. This page centralizes secrets away from Model Registry bindings and Knowledge Store configs.

## Scope
- Tenant-only credential management (no global credentials UI).
- CRUD for integration credentials with category grouping.
- Credentials are write-only in the UI (values are never read back).

## UI Sections
### 1. LLM Providers
- Stores API keys, base URLs, org IDs, and variants (e.g., `azure`, `org_abc`).
- Used by Model Registry bindings for chat, completion, embedding, and rerank.

### 2. Vector Stores
- Stores API keys, URLs, environment, and region for vector DBs (Pinecone, Qdrant, pgvector where applicable).
- Used by Knowledge Stores at runtime to configure adapters.

### 3. Artifact Secrets
- Stores secrets for custom artifacts or external handlers.
- Referenced by artifact config via credential IDs.

### 4. Custom Credentials
- Tenant-specific credentials for bespoke integrations.

## Data Model Mapping
### IntegrationCredential
- `category`: `llm_provider` | `vector_store` | `artifact_secret` | `custom`
- `provider_key`: canonical provider identifier (e.g., `openai`, `pinecone`)
- `provider_variant`: optional (e.g., `azure`, `org_abc`)
- `credentials`: JSON (write-only)
- `is_enabled`: toggles runtime availability

### Model Registry Binding
- `ModelProviderBinding.credentials_ref` points to IntegrationCredential.
- Resolver priority: `credentials_ref` → provider+variant → legacy ProviderConfig → binding config fallback.

### Knowledge Store
- `KnowledgeStore.credentials_ref` points to IntegrationCredential (vector store category).
- Backend adapter merges credentials at runtime.

## Security Requirements
- Secrets are never returned in GET responses.
- UI shows credential keys only (e.g., `api_key`, `base_url`).
- Delete is blocked if a credential is referenced by a model binding or knowledge store.

## API Surface
- `GET /admin/settings/credentials`
- `POST /admin/settings/credentials`
- `PATCH /admin/settings/credentials/{id}`
- `DELETE /admin/settings/credentials/{id}`
- `GET /admin/settings/credentials/status`

## Notes
- ProviderConfig remains as legacy fallback only.
- Credentials should be tenant scoped; super-admin global management is out of scope.
