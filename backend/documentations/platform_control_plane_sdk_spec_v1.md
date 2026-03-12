# Platform Control Plane SDK Contract Specification (v1)

Last Updated: 2026-03-12

## Document Control
- Status: In implementation (normative for new SDK work)
- Spec ID: `CONTROL-SDK-CONTRACT-v1`
- Primary audience: backend platform engineers, SDK maintainers, architect-agent/tooling engineers
- Canonical domain: platform control plane (admin/configuration/execution APIs), not hosted-runtime SDK

## 1. Purpose
This document defines the canonical SDK contract for controlling platform resources.

The same contract MUST be used by:
- Developer SDK clients (Python and TypeScript)
- Platform Architect runtime tools (agent callable tools)
- UI control-plane clients (service layer)

This removes contract drift between UI, SDK, and autonomous agent flows.

## 2. Scope and Non-Goals
### In Scope
- Full control-plane resource coverage for:
  - Agent lifecycle and runs
  - Tool registry
  - Artifact lifecycle and testing
  - RAG visual pipelines, compilation, jobs, step data access
  - Model registry and provider bindings
  - Integration credentials
  - Knowledge stores
  - Workload delegation/auth broker operations
  - Internal orchestration primitives (feature-gated)
  - Workload security approvals
- Method-level SDK contracts, payload shapes, error model, auth/tenant/idempotency requirements
- 1:1 SDK method to agent tool action parity

### Out of Scope
- Hosted app runtime SDK (`packages/runtime-sdk`) behavior
- Frontend UI rendering details
- OpenAPI generation mechanics beyond required outputs
- Legacy Mongo behavior

## 3. Normative Language
The terms MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.

## 4. Grounded Baseline (Current Implementation)
This v1 spec is grounded in current backend code:
- Router mounting in `backend/main.py` currently exposes mixed prefixes:
  - `/agents`, `/tools`, `/models`
  - `/admin/pipelines/*`, `/admin/artifacts`, `/admin/settings/*`, `/admin/knowledge-stores/*`
  - `/internal/auth/*`, `/internal/orchestration/*`
- Current lightweight Python SDK in `backend/sdk/` is catalog-first and not a full contract SDK.
- `backend/sdk/pipeline.py` now posts agent creation to canonical `/agents` (legacy package remains pending deletion).
- `backend/artifacts/builtin/platform_sdk/handler.py` now uses explicit-action, SDK-backed domain wrappers and no `/api/agents` fallback.
- Platform SDK runtime no longer auto-defaults empty calls to synthetic actions in `backend/app/agent/executors/standard.py`.
- Knowledge stores currently require `tenant_slug` query parameter, unlike most other domains.
- Duplicate `GET /agents/operators` router exposure has been removed (single authoritative route remains).

This spec defines the target canonical behavior and migration rules from these drifts.

## 5. Architecture Model
### 5.1 Canonical Model
- Canonical runtime truth: database-backed control-plane resources
- Canonical contract: this SDK schema/method spec
- Multiple authoring surfaces:
  - UI = visual authoring
  - SDK = programmatic authoring
  - Architect agent = autonomous authoring
- Single execution backend for all surfaces

### 5.2 Layering
- Layer A: versioned contract schemas
- Layer B: control-plane API handlers and services
- Layer C: SDK clients (Python/TS)
- Layer D: tool wrappers (agent-callable) generated/adapted from SDK methods

### 5.3 SDK Separation Rule
- `@talmudpedia/runtime-sdk` remains runtime/hosted-app focused
- New control-plane SDK is a separate package family for admin/resource operations

## 6. Package and Namespace Specification
### 6.1 Package Names
- Python: `talmudpedia_control_sdk`
- TypeScript: `@talmudpedia/control-sdk`

### 6.2 Required Modules
- `catalog`
- `agents`
- `tools`
- `artifacts`
- `rag`
- `models`
- `credentials`
- `knowledge_stores`
- `workload_security`
- `auth`
- `orchestration` (internal/gated)

### 6.3 Shared Client Configuration
Required client options:
- `base_url`
- `token_provider`
- `tenant_resolver` or explicit `tenant_id`
- `timeout`
- `retry_policy`
- `user_agent`
- `default_request_metadata`

## 7. Transport Contract
### 7.1 Base URL
All SDK methods target control-plane REST endpoints under configured `base_url`.

### 7.2 Required Headers
- `Authorization: Bearer <token>`
- `X-Tenant-ID: <uuid>` when endpoint uses tenant header semantics
- `X-Idempotency-Key: <string>` for mutation calls (MUST for v1 SDK mutations)
- `X-SDK-Contract: 1`
- `X-Request-ID` (optional; SDK SHOULD generate if omitted)

### 7.3 Auth Modes
- User principal token mode
- Delegated workload token mode (minted via internal auth endpoints)

### 7.4 Tenant Semantics
- SDK callers MUST provide explicit tenant context.
- SDK MUST NOT rely on server fallback to “first tenant”.
- For compatibility endpoints requiring `tenant_slug`, SDK resolves and passes slug explicitly until migrated.

### 7.5 Mutation Controls
Every mutating SDK method MUST support:
- `idempotency_key`
- `dry_run`
- `validate_only`
- `request_metadata`

### 7.6 Pagination
Collection methods MUST expose:
- `skip`
- `limit`
- optional filter parameters

### 7.7 Long-running Operations
For async execution methods, SDK SHOULD return operation/run identifiers and helpers (`poll`, `wait`).

## 8. Common Envelopes
### 8.1 SDK Request Options
```json
{
  "idempotency_key": "string",
  "dry_run": false,
  "validate_only": false,
  "request_metadata": {
    "reason": "string",
    "source": "ui|sdk|agent-tool|system",
    "trace_id": "string",
    "actor_hint": "string"
  }
}
```

### 8.2 SDK Response Envelope
```json
{
  "data": {},
  "meta": {
    "request_id": "string",
    "trace_id": "string",
    "idempotency_reused": false,
    "warnings": []
  },
  "errors": []
}
```

### 8.3 Error Shape
```json
{
  "code": "VALIDATION_ERROR",
  "message": "Human-readable error",
  "details": {},
  "retryable": false,
  "http_status": 422
}
```

## 9. Error Codes
Required stable error codes (minimum set):
- `VALIDATION_ERROR`
- `MISSING_REQUIRED_FIELD`
- `INVALID_ARGUMENT`
- `UNAUTHORIZED`
- `SCOPE_DENIED`
- `TENANT_MISMATCH`
- `NOT_FOUND`
- `CONFLICT`
- `ALREADY_EXISTS`
- `SENSITIVE_ACTION_APPROVAL_REQUIRED`
- `FEATURE_DISABLED`
- `RATE_LIMITED`
- `UPSTREAM_ERROR`
- `INTERNAL_ERROR`

Retryability guidance:
- Retryable: `RATE_LIMITED`, transient `UPSTREAM_ERROR`, selected `INTERNAL_ERROR`
- Non-retryable: validation/auth/scope/tenant/not-found/conflict class errors

## 10. Canonical Resource Schemas
This section defines contract-level resource types used by SDK methods and tool wrappers.

### 10.1 AgentSpec
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "string",
  "slug": "string",
  "description": "string|null",
  "graph_definition": {
    "spec_version": "string|null",
    "nodes": [],
    "edges": []
  },
  "memory_config": {},
  "execution_constraints": {},
  "status": "draft|published|archived|disabled",
  "version": 1,
  "is_active": true,
  "is_public": false,
  "created_at": "datetime",
  "updated_at": "datetime",
  "published_at": "datetime|null"
}
```

### 10.2 AgentRun
```json
{
  "id": "uuid",
  "status": "queued|running|completed|failed|paused|cancelled",
  "result": {},
  "error": "string|null",
  "lineage": {
    "root_run_id": "uuid|null",
    "parent_run_id": "uuid|null",
    "parent_node_id": "string|null",
    "depth": 0,
    "spawn_key": "string|null",
    "orchestration_group_id": "uuid|null"
  }
}
```

### 10.3 ToolSpec
```json
{
  "id": "uuid",
  "tenant_id": "uuid|null",
  "name": "string",
  "slug": "string",
  "description": "string|null",
  "scope": "tenant|global",
  "input_schema": {},
  "output_schema": {},
  "config_schema": {},
  "implementation_type": "custom|internal|artifact|mcp|rag_retrieval",
  "status": "draft|published|disabled",
  "version": "semver",
  "is_active": true,
  "is_system": false,
  "published_at": "datetime|null",
  "artifact_id": "string|null",
  "artifact_version": "string|null"
}
```

### 10.4 ArtifactSpec
```json
{
  "id": "string",
  "type": "draft|promoted|builtin",
  "scope": "rag|agent|both",
  "name": "string",
  "display_name": "string",
  "description": "string|null",
  "category": "string",
  "input_type": "string",
  "output_type": "string",
  "version": "string",
  "python_code": "string|null",
  "config_schema": [],
  "reads": [],
  "writes": [],
  "tags": [],
  "path": "string|null",
  "updated_at": "datetime"
}
```

### 10.5 RagVisualPipelineSpec
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "org_unit_id": "uuid|null",
  "name": "string",
  "description": "string|null",
  "pipeline_type": "ingestion|retrieval|...",
  "nodes": [],
  "edges": [],
  "version": 1,
  "is_published": false,
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 10.6 RagExecutablePipelineSpec
```json
{
  "id": "uuid",
  "visual_pipeline_id": "uuid",
  "tenant_id": "uuid",
  "version": 1,
  "compiled_graph": {},
  "pipeline_type": "string",
  "is_valid": true,
  "created_at": "datetime"
}
```

### 10.7 PipelineJobSpec
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "executable_pipeline_id": "uuid",
  "status": "queued|running|completed|failed",
  "input_params": {},
  "output": {},
  "error_message": "string|null",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 10.8 ModelSpec and ProviderBinding
```json
{
  "id": "uuid",
  "tenant_id": "uuid|null",
  "name": "string",
  "slug": "string",
  "description": "string|null",
  "capability_type": "chat|embedding|...",
  "status": "draft|published|deprecated|disabled",
  "version": 1,
  "metadata": {},
  "default_resolution_policy": {},
  "is_active": true,
  "is_default": false,
  "providers": [
    {
      "id": "uuid",
      "provider": "string",
      "provider_model_id": "string",
      "priority": 0,
      "is_enabled": true,
      "config": {},
      "credentials_ref": "uuid|null"
    }
  ]
}
```

### 10.9 CredentialSpec
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "category": "llm|vector_store|...",
  "provider_key": "string",
  "provider_variant": "string|null",
  "display_name": "string",
  "credential_keys": ["string"],
  "is_enabled": true,
  "is_default": false,
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 10.10 KnowledgeStoreSpec
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "string",
  "description": "string|null",
  "embedding_model_id": "string",
  "chunking_strategy": {},
  "retrieval_policy": "semantic_only|hybrid|keyword_only|recency_boosted",
  "backend": "pgvector|pinecone|qdrant|...",
  "credentials_ref": "uuid|null",
  "status": "active|archived|error",
  "document_count": 0,
  "chunk_count": 0
}
```

### 10.11 DelegationGrant and WorkloadToken
```json
{
  "grant_id": "uuid",
  "principal_id": "uuid",
  "effective_scopes": ["string"],
  "expires_at": "datetime",
  "approval_required": false
}
```

```json
{
  "token": "jwt",
  "token_type": "Bearer",
  "scope": ["string"],
  "expires_at": "datetime"
}
```

## 11. Method Contracts (Full Coverage)
The method list below is normative for v1 SDK surface. Each method maps to one control-plane operation.

### 11.1 `catalog`
- `catalog.get_rag_operator_catalog(tenant_slug?)`
  - Route: `GET /admin/pipelines/catalog`
  - Scope: `pipelines.catalog.read`
- `catalog.get_rag_operator(operator_id, tenant_slug?)`
  - Route: `GET /admin/pipelines/operators/{operator_id}`
- `catalog.list_rag_operators(tenant_slug?)`
  - Route: `GET /admin/pipelines/operators`
- `catalog.list_agent_operators()`
  - Route: `GET /agents/operators`
  - Note: duplicate route definitions currently exist; canonical endpoint remains singular.

### 11.2 `agents`
- `agents.list(status?, skip=0, limit=50, compact=false)`
  - Route: `GET /agents`
- `agents.create(spec, options)`
  - Route: `POST /agents`
  - Scope: `agents.write`
- `agents.get(agent_id)`
  - Route: `GET /agents/{agent_id}`
- `agents.update(agent_id, patch, options)`
  - Route: `PUT/PATCH /agents/{agent_id}`
  - Scope: `agents.write`
- `agents.update_graph(agent_id, graph, options)`
  - Route: `PUT /agents/{agent_id}/graph`
  - Scope: `agents.write`
- `agents.delete(agent_id, options)`
  - Route: `DELETE /agents/{agent_id}`
  - Scope: `agents.write`
  - Sensitive action approval for workload principals
- `agents.validate(agent_id)`
  - Route: `POST /agents/{agent_id}/validate`
  - Scope: `agents.run_tests`
- `agents.publish(agent_id, options)`
  - Route: `POST /agents/{agent_id}/publish`
  - Scope: `agents.write`
  - Sensitive action approval for workload principals
- `agents.list_versions(agent_id)`
  - Route: `GET /agents/{agent_id}/versions`
- `agents.get_version(agent_id, version)`
  - Route: `GET /agents/{agent_id}/versions/{version}`
- `agents.execute(agent_id, input)`
  - Route: `POST /agents/{agent_id}/execute`
  - Scope: `agents.execute`
- `agents.stream(agent_id, input, mode?)`
  - Route: `POST /agents/{agent_id}/stream`
  - Scope: `agents.execute`
  - Returns SSE stream
- `agents.start_run(agent_id, input)`
  - Route: `POST /agents/{agent_id}/run`
  - Scope: `agents.execute`
- `agents.resume_run(run_id, payload)`
  - Route: `POST /agents/runs/{run_id}/resume`
  - Scope: `agents.execute`
- `agents.get_run(run_id, include_tree=false)`
  - Route: `GET /agents/runs/{run_id}`
  - Scope: `agents.execute`
- `agents.get_run_tree(run_id)`
  - Route: `GET /agents/runs/{run_id}/tree`
  - Scope: `agents.execute`

### 11.3 `tools`
- `tools.list(scope?, is_active?, status?, implementation_type?, tool_type?, skip=0, limit=50)`
  - Route: `GET /tools`
- `tools.list_builtin_catalog(skip=0, limit=100)`
  - Route: `GET /tools/builtins/templates`
- `tools.create(spec, options)`
  - Route: `POST /tools`
  - Scope: `tools.write`
- `tools.get(tool_id)`
  - Route: `GET /tools/{tool_id}`
- `tools.update(tool_id, patch, options)`
  - Route: `PUT /tools/{tool_id}`
  - Scope: `tools.write`
- `tools.publish(tool_id, options)`
  - Route: `POST /tools/{tool_id}/publish`
  - Scope: `tools.write`
  - Sensitive action approval for workload principals
- `tools.create_version(tool_id, new_version, options)`
  - Route: `POST /tools/{tool_id}/version?new_version=...`
  - Scope: `tools.write`
- `tools.delete(tool_id, options)`
  - Route: `DELETE /tools/{tool_id}`
  - Scope: `tools.write`
  - Sensitive action approval for workload principals

### 11.4 `artifacts`
- Current hard-cut note:
  - Artifact authoring is now canonical revision-backed CRUD/test/publish.
  - Do not use legacy draft/promote method names in new work.
- `artifacts.list(tenant_slug?)`
  - Route: `GET /admin/artifacts`
- `artifacts.get(artifact_id, tenant_slug?)`
  - Route: `GET /admin/artifacts/{artifact_id}`
- `artifacts.create(spec, tenant_slug?, options)`
  - Route: `POST /admin/artifacts`
  - Scope: `artifacts.write`
- `artifacts.update(artifact_id, patch, tenant_slug?, options)`
  - Route: `PUT /admin/artifacts/{artifact_id}`
  - Scope: `artifacts.write`
- `artifacts.convert_kind(artifact_id, request, tenant_slug?, options)`
  - Route: `POST /admin/artifacts/{artifact_id}/convert-kind`
  - Scope: `artifacts.write`
- `artifacts.delete(artifact_id, tenant_slug?, options)`
  - Route: `DELETE /admin/artifacts/{artifact_id}`
  - Scope: `artifacts.write`
  - Sensitive action approval for workload principals
- `artifacts.publish(artifact_id, tenant_slug?, options)`
  - Route: `POST /admin/artifacts/{artifact_id}/publish`
  - Scope: `artifacts.write`
  - Sensitive action approval for workload principals
- `artifacts.create_test_run(request, tenant_slug?)`
  - Route: `POST /admin/artifacts/test-runs`

### 11.5 `rag`
- `rag.get_operator_catalog(tenant_slug?)`
  - Route: `GET /admin/pipelines/catalog`
  - Scope: `pipelines.catalog.read`
- `rag.list_visual_pipelines(tenant_slug?)`
  - Route: `GET /admin/pipelines/visual-pipelines`
- `rag.create_visual_pipeline(spec, tenant_slug?, options)`
  - Route: `POST /admin/pipelines/visual-pipelines`
  - Scope: `pipelines.write`
- `rag.get_visual_pipeline(pipeline_id, tenant_slug?)`
  - Route: `GET /admin/pipelines/visual-pipelines/{pipeline_id}`
- `rag.update_visual_pipeline(pipeline_id, patch, tenant_slug?, options)`
  - Route: `PUT /admin/pipelines/visual-pipelines/{pipeline_id}`
  - Scope: `pipelines.write`
- `rag.delete_visual_pipeline(pipeline_id, tenant_slug?, options)`
  - Route: `DELETE /admin/pipelines/visual-pipelines/{pipeline_id}`
  - Scope: `pipelines.write`
  - Sensitive action approval for workload principals
- `rag.compile_visual_pipeline(pipeline_id, tenant_slug?, options)`
  - Route: `POST /admin/pipelines/visual-pipelines/{pipeline_id}/compile`
  - Scope: `pipelines.write`
- `rag.list_pipeline_versions(pipeline_id, tenant_slug?)`
  - Route: `GET /admin/pipelines/visual-pipelines/{pipeline_id}/versions`
- `rag.get_executable_pipeline(exec_id, tenant_slug?)`
  - Route: `GET /admin/pipelines/executable-pipelines/{exec_id}`
- `rag.get_executable_input_schema(exec_id, tenant_slug?)`
  - Route: `GET /admin/pipelines/executable-pipelines/{exec_id}/input-schema`
- `rag.upload_input_file(file, tenant_slug)`
  - Route: `POST /admin/pipelines/pipeline-inputs/upload`
- `rag.create_job(executable_pipeline_id, input_params, tenant_slug)`
  - Route: `POST /admin/pipelines/jobs`
- `rag.list_jobs(filters)`
  - Route: `GET /admin/pipelines/jobs`
- `rag.get_job(job_id)`
  - Route: `GET /admin/pipelines/jobs/{job_id}`
- `rag.list_job_steps(job_id, lite=true)`
  - Route: `GET /admin/pipelines/jobs/{job_id}/steps`
- `rag.get_step_data(job_id, step_id, type, page=1, limit=20)`
  - Route: `GET /admin/pipelines/jobs/{job_id}/steps/{step_id}/data`
- `rag.get_step_field(job_id, step_id, type, path, offset=0, limit=100000)`
  - Route: `GET /admin/pipelines/jobs/{job_id}/steps/{step_id}/field`

### 11.6 `models`
- `models.list(capability_type?, is_active=true, skip=0, limit=50)`
  - Route: `GET /models`
- `models.create(spec, options)`
  - Route: `POST /models`
- `models.get(model_id)`
  - Route: `GET /models/{model_id}`
- `models.update(model_id, patch, options)`
  - Route: `PUT /models/{model_id}`
- `models.delete(model_id, options)`
  - Route: `DELETE /models/{model_id}`
- `models.add_provider(model_id, spec, options)`
  - Route: `POST /models/{model_id}/providers`
- `models.update_provider(model_id, provider_id, patch, options)`
  - Route: `PATCH /models/{model_id}/providers/{provider_id}`
- `models.delete_provider(model_id, provider_id, options)`
  - Route: `DELETE /models/{model_id}/providers/{provider_id}`

### 11.7 `credentials`
- `credentials.list(category?)`
  - Route: `GET /admin/settings/credentials`
- `credentials.create(spec, options)`
  - Route: `POST /admin/settings/credentials`
- `credentials.update(credential_id, patch, options)`
  - Route: `PATCH /admin/settings/credentials/{credential_id}`
- `credentials.delete(credential_id, force_disconnect=false, options)`
  - Route: `DELETE /admin/settings/credentials/{credential_id}`
- `credentials.usage(credential_id)`
  - Route: `GET /admin/settings/credentials/{credential_id}/usage`
- `credentials.status()`
  - Route: `GET /admin/settings/credentials/status`

### 11.8 `knowledge_stores`
- `knowledge_stores.list(tenant_slug)`
  - Route: `GET /admin/knowledge-stores`
- `knowledge_stores.create(spec, tenant_slug, options)`
  - Route: `POST /admin/knowledge-stores`
- `knowledge_stores.get(store_id, tenant_slug?)`
  - Route: `GET /admin/knowledge-stores/{store_id}`
- `knowledge_stores.update(store_id, patch, tenant_slug?, options)`
  - Route: `PATCH /admin/knowledge-stores/{store_id}`
- `knowledge_stores.delete(store_id, tenant_slug?, options)`
  - Route: `DELETE /admin/knowledge-stores/{store_id}`
- `knowledge_stores.stats(store_id, tenant_slug?)`
  - Route: `GET /admin/knowledge-stores/{store_id}/stats`

### 11.9 `workload_security`
- `workload_security.list_pending_scope_policies()`
  - Route: `GET /admin/security/workloads/pending`
  - Scope: `tools.write`
- `workload_security.approve_scope_policy(principal_id, approved_scopes)`
  - Route: `POST /admin/security/workloads/principals/{principal_id}/approve`
  - Scope: `tools.write`
- `workload_security.reject_scope_policy(principal_id)`
  - Route: `POST /admin/security/workloads/principals/{principal_id}/reject`
  - Scope: `tools.write`
- `workload_security.list_action_approvals(filters?)`
  - Route: `GET /admin/security/workloads/approvals`
  - Scope: `tools.write`
- `workload_security.decide_action_approval(payload)`
  - Route: `POST /admin/security/workloads/approvals/decide`
  - Scope: `tools.write`

### 11.10 `auth`
- `auth.create_delegation_grant(payload)`
  - Route: `POST /internal/auth/delegation-grants`
- `auth.mint_workload_token(payload)`
  - Route: `POST /internal/auth/workload-token`
- `auth.get_workload_jwks()`
  - Route: `GET /.well-known/jwks.json`

### 11.11 `orchestration` (feature-gated)
- `orchestration.spawn_run(payload, options)`
  - Route: `POST /internal/orchestration/spawn-run`
  - Scope: `agents.execute`
- `orchestration.spawn_group(payload, options)`
  - Route: `POST /internal/orchestration/spawn-group`
  - Scope: `agents.execute`
- `orchestration.join(payload, options)`
  - Route: `POST /internal/orchestration/join`
  - Scope: `agents.execute`
- `orchestration.cancel_subtree(payload, options)`
  - Route: `POST /internal/orchestration/cancel-subtree`
  - Scope: `agents.execute`
- `orchestration.evaluate_and_replan(payload, options)`
  - Route: `POST /internal/orchestration/evaluate-and-replan`
  - Scope: `agents.execute`
- `orchestration.query_tree(run_id)`
  - Route: `GET /internal/orchestration/runs/{run_id}/tree`
  - Scope: `agents.execute`

## 12. Agent Tool Parity
### 12.1 Rule
Every SDK method above MUST have an equivalent agent tool action with the same JSON input and output contracts.

### 12.2 Current Tool Action Baseline
Current control-plane tooling supports canonical domain actions and legacy aliases:
- Canonical `domain.action` dispatch (for example `agents.create`, `agents.update`, `rag.create_visual_pipeline`, `rag.compile_visual_pipeline`, `auth.mint_workload_token`, `workload_security.decide_approval`).
- Legacy aliases remain for compatibility in `builtin/platform_sdk` (`fetch_catalog`, `create_artifact_draft`, etc.) but are non-canonical.

Platform Architect v1 now uses domain-scoped tools:
- `platform-rag`
- `platform-agents`
- `platform-assets`
- `platform-governance`

Each domain tool enforces action-prefix boundaries with explicit action payload contracts.
Hard-cut note: `architect.run` is removed from active runtime path.

### 12.3 v1 Required Direction
- Move from planner-centric coarse actions to domain actions that map directly to SDK methods.
- Tool wrappers MUST NOT perform hidden route fallbacks (`/agents` to `/api/agents`) or hidden action defaulting.
- Missing action MUST return structured validation error.

## 13. Security and Authorization Requirements
### 13.1 Scope Enforcement
SDK method docs MUST declare required scope(s). Tool wrappers MUST enforce the same scopes.

### 13.2 Delegated Workload Flow
For privileged workload calls:
1. Create delegation grant (`/internal/auth/delegation-grants`)
2. Mint workload token (`/internal/auth/workload-token`)
3. Call target control-plane methods with minted token

### 13.3 Sensitive Mutations
Operations guarded by `ensure_sensitive_action_approved` require explicit approval records for workload principals.

### 13.4 Tenant Isolation
All methods MUST be tenant-scoped. Cross-tenant access without wildcard scope MUST fail with `TENANT_MISMATCH`/403.

## 14. Idempotency and Dry-Run Behavior
### 14.1 Mutations
All SDK mutation methods MUST accept idempotency keys.

### 14.2 Server Behavior
- Same idempotency key + same effective payload returns stable result with `meta.idempotency_reused=true`.
- Same idempotency key + different payload returns conflict error.

### 14.3 Dry-run
`dry_run=true` MUST execute validation and authorization checks but MUST NOT persist mutations.

## 15. Observability and Audit
Mutation methods MUST emit audit events with:
- actor type and identifier
- tenant id
- resource type and id
- action
- idempotency key
- trace id/request id
- diff summary where available

SDK clients SHOULD expose returned trace/request IDs for downstream logging.

## 16. Versioning and Compatibility
### 16.1 Contract Version
- Request header: `X-SDK-Contract: 1`
- SDK major version maps to contract major version.

### 16.2 Compatibility
- Additive fields are backward compatible.
- Field removals/semantic changes require next major contract version.
- Deprecated methods/endpoints MUST be announced and logged before removal.

## 17. Conformance Test Requirements
A contract test suite MUST validate:
- Method serialization/deserialization for all modules
- Scope and tenant enforcement
- Idempotency behavior
- Dry-run non-persistence
- Error code stability
- Tool parity: SDK call and tool action produce equivalent outcomes
- Cross-surface parity: UI path, SDK path, tool path converge to same persisted state

## 18. Migration Plan
### Phase 0: Contract Freeze
- Finalize schema package and this method surface.
- Freeze route aliases and publish canonical route map.

### Phase 1: SDK Implementation
- Implement Python and TS SDKs for read + core write methods first.
- Add generated types and transport layer with envelopes/error mapping.

### Phase 2: Tool Adapter Migration
- Replace ad-hoc `builtin/platform_sdk` internals with SDK-backed wrappers.
- Remove hidden defaults and fallback heuristics.

### Phase 3: Surface Normalization
- Normalize tenant semantics across all modules.
- Add uniform envelope/idempotency behavior on control-plane writes.

### Phase 4: Deprecation Cleanup
- Remove legacy wrapper package (`backend/sdk/`)
- Remove `/api/agents` compatibility path from SDK/tool flows
- Remove duplicate route definitions and stale docs/tests

## 19. Cleanup and Additions for This Migration
### 19.1 Remove/Clean
- Legacy dynamic SDK package: `backend/sdk/*` after replacement parity is achieved.
- Route fallback logic in `backend/artifacts/builtin/platform_sdk/handler.py` (`/agents` and `/api/agents`).
- Empty Platform SDK call action-defaulting in `backend/app/agent/executors/standard.py`.
- Duplicate `GET /agents/operators` route definitions across routers.
- Per-module frontend endpoint quirks once frontend uses generated control SDK client.

### 19.2 Add
- New canonical control-plane SDK packages (Python + TS) with full module coverage.
- Shared versioned schema package used by routers, SDKs, and tool wrappers.
- Uniform response/error envelope middleware or shared response layer.
- Idempotency support for all mutating endpoints.
- Tool-wrapper generator from SDK method metadata.
- Tenant lifecycle seeding hook for baseline resources (instead of first-tenant startup assumption).
- Contract conformance suite and parity tests.

## 20. Known Contradictions to Resolve
- Existing tests/docs may assume internal auth fallback behavior in Platform SDK handler that is not present in current implementation.
- Knowledge-store tenant context and HTTP method assumptions differ across clients; canonical SDK must use backend-defined `PATCH` update semantics.
- Some routers currently rely on implicit tenant fallback logic; canonical SDK requires explicit tenant context.

## 21. Implementation Start Set (Recommended)
First increment SHOULD implement these modules end-to-end with full tests:
- `agents`
- `tools`
- `artifacts`

Then expand to:
- `rag`
- `models`
- `credentials`
- `knowledge_stores`
- `auth`
- `orchestration`
- `workload_security`

## 22. Appendix: Proposed Canonical Domain Actions (for SDK + Tool Layer)
The following action IDs are recommended as stable domain actions for parity:
- `catalog.list_capabilities`
- `agents.list`, `agents.get`, `agents.create_or_update`, `agents.publish`, `agents.validate`, `agents.execute`, `agents.start_run`, `agents.resume_run`, `agents.get_run`, `agents.get_run_tree`
- `tools.list`, `tools.get`, `tools.create_or_update`, `tools.publish`, `tools.create_version`, `tools.delete`
- `artifacts.list`, `artifacts.get`, `artifacts.create`, `artifacts.update`, `artifacts.convert_kind`, `artifacts.publish`, `artifacts.delete`, `artifacts.create_test_run`
- `rag.list_pipelines`, `rag.create_or_update_pipeline`, `rag.compile_pipeline`, `rag.create_job`, `rag.get_job`, `rag.get_step_data`
- `models.list`, `models.create_or_update`, `models.add_provider`, `models.update_provider`, `models.delete_provider`
- `credentials.list`, `credentials.create_or_update`, `credentials.delete`, `credentials.usage`, `credentials.status`
- `knowledge_stores.list`, `knowledge_stores.create_or_update`, `knowledge_stores.delete`, `knowledge_stores.stats`
- `auth.create_delegation_grant`, `auth.mint_workload_token`
- `orchestration.spawn_run`, `orchestration.spawn_group`, `orchestration.join`, `orchestration.cancel_subtree`, `orchestration.evaluate_and_replan`, `orchestration.query_tree`
- `workload_security.list_pending`, `workload_security.approve_policy`, `workload_security.reject_policy`, `workload_security.list_approvals`, `workload_security.decide_approval`

## 23. Implementation Progress (2026-03-01)
Completed in this increment:
- Activated/wired Python control-plane SDK package usage: `backend/talmudpedia_control_sdk/`.
- Adopted shared transport/error/envelope client (`ControlPlaneClient`) with contract headers (`X-SDK-Contract`, tenant/auth, idempotency on mutations) in platform tool flows.
- Added shared client configuration features aligned with spec section 6.3:
  - `tenant_resolver` callback support (alternative to fixed `tenant_id`)
  - `ControlPlaneClient.from_env(...)` bootstrap for base URL, token, tenant
- SDK module coverage in Python package now includes:
  - `catalog`
  - `agents`
  - `tools`
  - `artifacts`
  - `rag`
  - `models`
  - `credentials`
  - `knowledge_stores`
  - `workload_security`
  - `auth`
  - `orchestration`
- Added RAG file upload support in SDK transport and `rag.upload_input_file(...)` method surface.
- Enforced explicit-action behavior in `backend/artifacts/builtin/platform_sdk/handler.py`:
  - Missing action now returns structured validation error.
  - Unknown action now returns structured `INVALID_ARGUMENT` style error payload.
- Removed legacy deploy-agent fallback to `/api/agents` from platform SDK execution path.
- Removed Platform SDK empty-call auto-defaulting from `backend/app/agent/executors/standard.py`.
- Removed duplicate `/agents/operators` route registration from `backend/main.py` by keeping `agents` router as the single mounted source.
- Removed planner-centric platform SDK actions from runtime dispatch:
  - `validate_plan`
  - `execute_plan`
- Migrated platform SDK handler routing to canonical domain actions with explicit alias normalization (legacy action IDs map to canonical dotted action IDs):
  - `catalog.*`
  - `artifacts.*`
  - `tools.*`
  - `agents.*`
  - `orchestration.*`
- Split platform SDK runtime into domain modules and reduced dispatcher size under guardrail:
  - `backend/artifacts/builtin/platform_sdk/handler.py` now acts as a thin dispatcher (~656 LOC).
  - Added `backend/artifacts/builtin/platform_sdk/actions/{catalog,agents,artifacts,tools,orchestration}.py`.
- Expanded canonical start-set action coverage in runtime dispatch:
  - Added read/write canonical handlers for `artifacts.*` (`list`, `get`, `delete`, `test` in addition to existing draft/promote).
  - Added read/write canonical handlers for `tools.*` (`list`, `get`, `publish`, `create_version`, `delete` in addition to existing create_or_update).
  - Added canonical handlers for `agents.*` (`list`, `get`, `create_or_update`, `publish`, `validate`, `start_run`, `resume_run`, `get_run`, `get_run_tree` in addition to execute/run_tests).
- Extended canonical dispatch coverage to non-start-set domain families:
  - `rag.*`: `list_pipelines`, `create_or_update_pipeline`, `compile_pipeline`, `create_job`, `get_job`, `get_step_data`
  - `models.*`: `list`, `create_or_update`, `add_provider`, `update_provider`, `delete_provider`
  - `credentials.*`: `list`, `create_or_update`, `delete`, `usage`, `status`
  - `knowledge_stores.*`: `list`, `create_or_update`, `delete`, `stats`
  - `auth.*`: `create_delegation_grant`, `mint_workload_token`
  - `workload_security.*`: `list_pending`, `approve_policy`, `reject_policy`, `list_approvals`, `decide_approval`
- Switched orchestration wrappers to direct `talmudpedia_control_sdk.orchestration.*` calls (no ad-hoc internal HTTP helper path for runtime dispatch).
- Added parity-focused tests that assert action inputs/outputs align with SDK method invocation contracts:
  - `backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py`
  - Expanded parity assertions to include newly exposed canonical actions (`tools.publish`, `artifacts.delete`, `agents.start_run`, `agents.get_run_tree`).
  - Added coverage for additional domain actions (`rag.create_job`, `models.update_provider`, `credentials.delete`, `knowledge_stores.list`, `auth.mint_workload_token`, `workload_security.decide_approval`).
  - Added broad matrix parity coverage in `backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py` for most remaining canonical dispatched actions across domain families.
  - Added canonical `agents.run_tests` action parity and a parity guard that fails when dispatched canonical actions are introduced without test coverage references.
- Added env-gated cross-surface parity integration test scaffold:
  - `backend/tests/platform_sdk_tool/test_platform_sdk_cross_surface_parity_integration.py`
  - Current coverage validates persisted-state equivalence for core mutations across UI HTTP path, SDK path, and tool-action path:
    - `artifacts.create`
    - `tools.create_or_update` (create)
    - `tools.create_or_update` (update)
    - `tools.publish`
    - `artifacts.publish`
    - `agents.create_or_update` (create)
    - `agents.publish`
- Added execution-focused cross-surface parity integration module:
  - `backend/tests/platform_sdk_tool/test_platform_sdk_cross_surface_parity_execution_integration.py`
  - Current coverage:
    - `agents.start_run` (success-path parity with persisted run retrieval)
    - `agents.resume_run` (error-path parity for nonexistent run ID)
- Added control-plane guardrail test to fail on new `/api/agents` references in SDK/tool Python code:
  - `backend/tests/control_plane_sdk/test_no_legacy_api_agents_refs.py`
- Archived legacy overlapping SDK doc as explicitly non-canonical:
  - `backend/documentations/sdk_specification.md`
- Added unit/contract tests for the new SDK and hard-cut behavior:
  - `backend/tests/control_plane_sdk/test_client_and_modules.py`
  - `backend/tests/control_plane_sdk/test_additional_modules.py`
  - `backend/tests/control_plane_sdk/test_http_integration.py` (env-gated HTTP smoke coverage)
  - `backend/tests/platform_sdk_tool/test_platform_sdk_actions.py` updates
  - `backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py` updates
  - `backend/tests/workload_delegation_auth/test_platform_sdk_delegated_auth_flow.py` updates

Still pending for full v1 conformance:
- TypeScript SDK package (`@talmudpedia/control-sdk`).
- Full tool-wrapper parity generation for all SDK methods (broader than current covered actions).
- Legacy package deletion (`backend/sdk/`) after full replacement parity.
- Cross-surface E2E parity suite (UI vs SDK vs tool wrappers) for all control-plane mutation paths.
- Production-facing developer docs for external SDK consumers (installation/versioning/auth quickstart) are still pending.

## 24. MVP Remaining Implementation Scope (Handoff Checklist)
This section defines the minimum remaining work to call the Control Plane SDK v1 migration MVP complete.

### 24.1 Critical (Must finish for MVP)
1. Split oversized platform handler into domain modules and enforce file-size guardrail:
   - Completed: `backend/artifacts/builtin/platform_sdk/handler.py` is now a thin dispatcher and domain handlers were split into:
     - `backend/artifacts/builtin/platform_sdk/actions/catalog.py`
     - `backend/artifacts/builtin/platform_sdk/actions/agents.py`
     - `backend/artifacts/builtin/platform_sdk/actions/artifacts.py`
     - `backend/artifacts/builtin/platform_sdk/actions/tools.py`
     - `backend/artifacts/builtin/platform_sdk/actions/orchestration.py`
2. Complete explicit 1:1 tool action coverage for all required canonical domain methods (no planner/coarse actions):
   - In progress: canonical domain families are now broadly covered across start-set and non-start-set modules (`catalog`, `agents`, `tools`, `artifacts`, `orchestration`, `rag`, `models`, `credentials`, `knowledge_stores`, `auth`, `workload_security`).
   - Remaining: close any still-uncovered method-level action gaps and ensure exact 1:1 parity evidence per action.
   - Keep alias support only as input normalization.
   - Runtime output action IDs must be canonical dotted IDs.
3. Expand action parity tests from partial coverage to full method-family coverage:
   - In progress: parity coverage now includes broad matrix assertions for most canonical dispatched actions across all currently routed domain families.
   - Remaining: close any still-missing action-level parity assertions and strengthen assertions from call-shape parity to payload/result equivalence where needed.
   - Every exposed tool action must have a direct parity test against corresponding SDK method call contract.
4. Add cross-surface parity tests for core mutation paths:
   - In progress: env-gated cross-surface parity now includes artifact, tool, and agent core mutations plus execution lifecycle coverage (`agents.start_run`, `agents.resume_run` error-path parity).
   - Remaining: increase success-path execution lifecycle depth (for resumable run states) and ensure execution in CI environments with integration credentials.
   - UI path vs SDK path vs tool path must converge to equivalent persisted state.
5. Delete legacy lightweight SDK package:
   - Remove `backend/sdk/*` once parity suite is green and no callers remain.
6. Ensure `/api/agents` guardrail is always enforced in CI:
   - The guardrail test exists and must be wired into always-on CI execution path.

### 24.2 Important (Should finish in same MVP window)
1. Method-level contract completion in this spec for every exposed method:
   - input schema
   - output schema
   - side effects
   - scopes
   - stable error codes
   - idempotency behavior
2. Normalize error envelope behavior across SDK wrappers/tool actions:
   - consistent `code`, `message`, `details`, `retryable`, `http_status`.
3. Validate audit-event emission coverage for all control-plane mutation wrappers.
4. Add env-gated HTTP parity integration tests for remaining uncovered module routes.

### 24.3 Nice-to-have (Not blocking MVP)
1. TypeScript control SDK package implementation parity with Python.
2. External-facing developer quickstart documentation and migration guide.
3. Optional action-wrapper generation from shared method metadata to reduce drift long-term.

### 24.4 MVP Exit Criteria (Operational)
MVP is complete only when all are true:
1. No planner-centric actions remain executable in platform SDK tool runtime.
2. No `/api/agents` references remain in control-plane SDK/tool code paths, and CI blocks regressions.
3. Legacy `backend/sdk/` package is deleted.
4. Full parity tests (action↔SDK and UI↔SDK↔tool for core mutations) pass.
5. Platform SDK tool runtime code is modularized and compliant with file-size guardrails.
6. Contract and hard-cut docs are synchronized with shipped behavior.
