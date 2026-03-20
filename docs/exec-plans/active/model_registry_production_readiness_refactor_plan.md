# Execution Plan: Model Registry Production Readiness Refactor

Last Updated: 2026-03-20

## Status: Proposed

This plan turns the current model registry into a production-ready control-plane subsystem with strict contracts, truthful runtime support, simple admin UX, and full integration coverage across the platform.

Initial seed-catalog cleanup already landed:
- stale seeded providers that the current resolver cannot execute were removed from `backend/app/db/postgres/seeds/models.json`
- the seed catalog now tracks a smaller current set of OpenAI, Google, Anthropic, and xAI chat models plus current OpenAI embeddings
- broader multi-provider expansion still belongs to the later provider-catalog and resolver-hardening slices in this plan

## Goals

- make the catalog truthful: no model/provider rows that cannot actually run
- make model identity strict and deterministic across the platform
- harden default-model, binding-selection, and credential-resolution semantics
- remove current API/UI drift between backend, frontend, and runtime consumers
- keep the user experience simple for admins
- add full backend, frontend, and integration test coverage for the registry and its downstream consumers

## UX Guardrails

- do not make admins type or reason about internal identifiers beyond UUID-backed selection
- do not expose raw JSON editors for common model-management tasks
- do not expose provider capabilities that the backend/runtime cannot enforce
- prefer a smaller honest surface over a larger configurable but misleading one

## Non-Goals

- building a customer-facing model marketplace
- preserving slug-based model lookup for backward compatibility
- supporting every possible provider immediately if the runtime cannot actually execute it safely

## Researched Current State

### What exists now

- logical models and provider bindings live in `backend/app/db/postgres/models/registry.py`
- CRUD routes exist in `backend/app/api/routers/models.py`
- runtime resolution exists in `backend/app/services/model_resolver.py`
- default model pointers live in `Tenant.settings` and are validated in `backend/app/api/routers/org_units.py`
- credentials precedence and disconnect behavior are tied into `backend/app/api/routers/settings.py`
- embeddings and vector-store integration depend on the model registry through `backend/app/services/retrieval_service.py`
- admin stats report model and provider-binding counts from `backend/app/api/routers/stats.py`
- frontend admin management exists in `frontend-reshet/src/app/admin/models/page.tsx`

### Current gaps that this plan must close

1. Seeded provider support is not truthful.
- `backend/app/db/postgres/seeds/models.json` seeds Anthropic, Groq, Together, Mistral, Cohere, and others.
- `backend/app/services/model_resolver.py` only instantiates a subset of providers for chat.

2. Model identity is ambiguous.
- model lookup currently accepts UUID, slug, or name
- the schema allows tenant and global rows to share the same slug
- slug lookup across tenant + global scope is therefore unsafe

3. Default-model semantics are under-specified.
- `is_default` is a plain boolean without a uniqueness guarantee per tenant/capability
- helper code assumes only one default exists

4. Binding selection and fallback behavior are brittle.
- tenant bindings outrank global bindings, but the current disabled-binding behavior can block otherwise valid fallbacks
- capability- and provider-specific policy is not modeled cleanly

5. API and UI contracts have already drifted.
- frontend model service still sends a `status` filter the backend list route does not implement
- backend list `total` does not fully match the filtered result set

6. Provider metadata is too thin.
- provider allowlisting exists
- provider capability metadata, required credential keys, supported config fields, and runtime constraints do not

7. Admin UX is too raw for a production control plane.
- slug is exposed as a required admin-authored field
- raw metadata and resolution-policy JSON are exposed directly in the main edit flow

8. Test coverage is shallow relative to the platform blast radius.
- existing tests cover only a narrow subset of credentials resolution, one provider-binding PATCH path, and a small UI surface

### Current downstream integration points that must stay aligned

- agent graph node `model_id` contracts in `docs/product-specs/agent_graph_spec.md`
- tenant default pointers in `docs/product-specs/settings_hub_spec.md`
- admin stats model/provider summaries in `docs/product-specs/admin_stats_spec.md`
- RAG embedding resolution and knowledge-store credential merging
- attachment vision checks
- agent execution `requested_model_id` and `resolved_model_id` persistence

### Current documentation drift to keep in mind

- `backend/documentations/agent_management_state.md` describes model-resolver integration as completed
- current code still has major support and contract gaps
- treat that legacy doc as stale for model-registry completeness claims

## Target End State

At the end of this refactor:

- model references inside the platform are UUID-only
- display is based on model `name`, not a user-managed slug
- if a stable non-UUID seed/import key is still needed, it is system-managed and not admin-authored
- every visible provider/model combination is executable and validated
- defaults are unique and deterministic
- binding resolution is explicit, capability-aware, and fully tested
- the admin UI uses simple structured controls rather than freeform JSON for common operations
- every downstream integration has dedicated regression coverage

## Slice Roadmap

## Slice 1: Identity Hard Cut

### Objective

Remove `slug` as a model identity mechanism and make UUID the only internal model reference.

### Why this comes first

- it removes the biggest source of lookup ambiguity
- it simplifies downstream contracts
- it makes tenant/global override rules explicit instead of accidental

### Scope

- remove model slug lookup from runtime services
- remove slug from `/models` create/edit/list DTOs
- remove slug from the admin models UI
- update seed/import logic to stop depending on user-authored slugs
- define whether a hidden system-managed `key` is needed for seed synchronization; if not, use UUID + seed migration logic only

### Touches

- `backend/app/db/postgres/models/registry.py`
- `backend/app/api/routers/models.py`
- `backend/app/services/model_resolver.py`
- `backend/app/services/runtime_attachment_service.py`
- `frontend-reshet/src/services/agent.ts`
- `frontend-reshet/src/services/models.ts`
- `frontend-reshet/src/app/admin/models/page.tsx`
- `backend/app/db/postgres/seeds/models.json`

### Acceptance criteria

- no model service accepts slug or name as a runtime identifier
- no admin flow asks users to create or edit a model slug
- no model lookup path can become ambiguous because of tenant/global duplication

### Required tests

- backend API tests for id-only model CRUD and lookup failure on legacy slug inputs
- migration tests for slug removal/backfill behavior
- frontend tests verifying create/edit flows work without slug fields

## Slice 2: Canonical Provider Catalog And Support Matrix

### Objective

Create one canonical provider catalog that defines what is supported, for which capabilities, and with what credential/config requirements.

### Why this is required

- current backend allowlisting is too shallow
- current frontend provider options are effectively static labels
- the seeded model catalog currently advertises unsupported runtime paths

### Scope

- replace the simple allowlist helper with a canonical provider manifest
- encode:
  - supported capabilities
  - required credential categories and keys
  - supported provider variants
  - supported config fields
  - runtime constraints such as temperature locking, vision support, tool-calling support, and reasoning-mode restrictions
- drive both backend validation and frontend provider-option rendering from the same canonical source
- prune or hide unsupported providers/models until their runtime adapters exist

### Touches

- `backend/app/services/integration_provider_catalog.py`
- `backend/app/services/model_temperature_policy.py`
- `frontend-reshet/src/services/provider-catalog.ts`
- seed catalog files and any model-management UI that exposes provider choices

### Acceptance criteria

- every provider option exposed in admin UI is backend-supported and validated
- every seeded model/provider binding is either runnable or absent
- capability-specific validation happens before persistence, not only at execution time

### Required tests

- provider-catalog contract tests
- validation tests for unsupported provider/capability combinations
- frontend tests confirming the UI only shows allowed providers for each capability

## Slice 3: Resolver Hardening And Runtime Truthfulness

### Objective

Make model resolution deterministic, explicit, fully adapter-backed, and production-safe.

### Scope

- implement or intentionally remove every currently seeded provider path
- harden tenant binding vs global binding precedence
- define disabled-binding semantics cleanly
- make fallback policy explicit instead of implicit row ordering
- validate model status and capability consistently for chat, embeddings, vision, audio, rerank, and future categories
- ensure `requested_model_id` and `resolved_model_id` remain UUID-backed and accurate across run records

### Touches

- `backend/app/services/model_resolver.py`
- `backend/app/agent/executors/standard.py`
- `backend/app/agent/executors/classify_executor.py`
- `backend/app/services/retrieval_service.py`
- `backend/app/rag/pipeline/operator_executor.py`
- `backend/app/agent/execution/service.py`
- `backend/app/services/runtime_attachment_service.py`

### Acceptance criteria

- resolver behavior is deterministic for every supported capability
- disabled tenant bindings do not create accidental dead ends unless explicitly intended by policy
- seeded chat and embedding models either resolve successfully or are not present in the catalog
- runtime traces and persisted run rows keep accurate resolved-model identity

### Required tests

- provider adapter coverage tests per supported provider/capability
- binding selection tests for:
  - tenant-only
  - global-only
  - tenant overrides global
  - multiple tenant bindings
  - disabled higher-priority binding with valid lower-priority binding
  - fallback enabled vs disabled
- integration tests covering agent execution, classify execution, RAG embedding resolution, and attachment vision gating

## Slice 4: Defaults, Uniqueness, And Control-Plane Invariants

### Objective

Encode the registry invariants in the schema and APIs instead of depending on convention.

### Scope

- enforce one default model per `tenant_id + capability_type`
- decide and enforce whether a global default per capability is allowed
- align `status` and `is_active` semantics or collapse them into one clear state model
- make `/models` list filtering and counts consistent
- validate provider-binding uniqueness and model/provider compatibility at write time

### Touches

- `backend/app/db/postgres/models/registry.py`
- model-related migrations
- `backend/app/api/routers/models.py`
- `backend/app/services/registry_seeding.py`
- `backend/app/api/routers/org_units.py`

### Acceptance criteria

- it is impossible to create multiple defaults for the same capability scope
- list responses and counts always agree
- control-plane writes fail fast on invalid state instead of allowing bad rows into the DB

### Required tests

- schema-level and API-level invariant tests
- settings-default tests for valid/invalid default pointers
- regression tests for duplicate-default rejection and consistent list counts

## Slice 5: Admin UX Simplification

### Objective

Keep the registry manageable for admins without exposing implementation details as primary inputs.

### Scope

- simplify create/edit flows to:
  - name
  - capability
  - active/default state
  - provider bindings
  - credential selection
  - simple policy toggles where needed
- remove raw metadata JSON from the main happy path
- remove raw resolution-policy JSON from the main happy path
- show only relevant provider fields for the selected capability/provider
- make credential linkage and “platform default” behavior explicit and understandable

### UX rule

Advanced/internal fields may still exist behind a narrow expert path if absolutely necessary, but they must not be the default authoring flow.

### Touches

- `frontend-reshet/src/app/admin/models/page.tsx`
- `frontend-reshet/src/app/admin/models/components/ProviderDialogs.tsx`
- `frontend-reshet/src/services/models.ts`
- corresponding backend DTO validation

### Acceptance criteria

- no primary admin flow requires raw JSON editing
- unsupported combinations are prevented in the UI before submit
- the UI communicates default/fallback/credential behavior clearly without explaining backend internals

### Required tests

- frontend interaction tests for normal CRUD flows
- frontend validation tests for provider/capability mismatch
- frontend settings-hub integration tests for default-model selection

## Slice 6: Downstream Integration Alignment

### Objective

Remove drift between the registry and the rest of the platform.

### Scope

- settings hub default-model validation
- credential usage inspection and force-disconnect cleanup
- RAG knowledge-store embedding model handling
- attachment vision-capability enforcement
- admin stats model and provider-binding reporting
- agent graph mutation paths that set `model_id`
- any SDK or service client contracts that still expose old model-registry fields

### Touches

- `backend/app/api/routers/org_units.py`
- `backend/app/api/routers/settings.py`
- `backend/app/api/routers/stats.py`
- `backend/app/services/retrieval_service.py`
- `backend/app/services/runtime_attachment_service.py`
- `backend/app/services/agent_graph_mutation_service.py`
- frontend settings/admin surfaces and service types

### Acceptance criteria

- every downstream consumer uses the same model identity and lifecycle contract
- credential deletion usage reports remain accurate for model bindings
- stats surfaces do not rely on fields removed from the model registry

### Required tests

- settings hub integration tests
- credential force-disconnect tests covering model bindings
- stats contract tests for models/resources sections
- RAG and attachment integration tests against real registry rows

## Slice 7: Seeding, Migration, And Rollout Safety

### Objective

Make the rollout safe, repeatable, and reversible at the data layer without keeping long-term compatibility clutter.

### Scope

- define the migration sequence for:
  - slug removal
  - default uniqueness
  - provider-catalog normalization
  - unsupported-seed cleanup
- rewrite seed synchronization to use the new identity rules
- add startup/seed assertions that fail on invalid catalog rows
- add one-shot audit tooling or assertions to surface bad historical rows before rollout

### Acceptance criteria

- fresh bootstrap creates only valid, runnable registry state
- migrated environments are normalized into the new invariant set
- no post-migration path depends on soft legacy fallback behavior

### Required tests

- migration tests against legacy-shaped rows
- seed-sync tests
- bootstrap regression tests for invalid seed definitions

## Slice 8: Full Coverage Test Program

### Objective

Give the model registry first-class test coverage equal to its platform blast radius.

### Test organization target

Backend:
- `backend/tests/model_registry_contract/`
- `backend/tests/model_registry_resolution/`
- `backend/tests/model_registry_integrations/`
- `backend/tests/model_registry_migrations/`

Frontend:
- `frontend-reshet/src/__tests__/models_registry/`
- `frontend-reshet/src/__tests__/settings_hub/`
- add focused model-related coverage under existing feature suites that consume model selection

Every new feature test directory must include `test_state.md`.

### Coverage matrix

Contract coverage:
- CRUD
- filters
- counts
- defaults
- permissions
- DTO shape

Resolution coverage:
- each supported provider/capability
- credential precedence
- tenant/global precedence
- fallback policy
- disabled/deprecated states
- missing-credential failure modes

Integration coverage:
- agent execution
- classify execution
- graph mutation model assignment
- settings defaults
- credentials usage and force disconnect
- RAG embedding resolution
- vector-store credential merge interactions
- attachment vision checks
- stats summaries

Frontend coverage:
- model registry page CRUD
- provider binding CRUD
- validation and empty/error states
- settings-hub default model selection
- model consumers that should react to catalog changes

Migration coverage:
- slug removal
- duplicate defaults
- invalid seed cleanup
- unsupported provider rows

### CI expectation

The final rollout should add registry-focused backend and frontend test commands to the normal quality gate, not leave them as optional ad hoc suites.

## Recommended Execution Order

1. Slice 1: Identity Hard Cut
2. Slice 2: Canonical Provider Catalog And Support Matrix
3. Slice 3: Resolver Hardening And Runtime Truthfulness
4. Slice 4: Defaults, Uniqueness, And Control-Plane Invariants
5. Slice 5: Admin UX Simplification
6. Slice 6: Downstream Integration Alignment
7. Slice 7: Seeding, Migration, And Rollout Safety
8. Slice 8: Full Coverage Test Program

## Release Gate

Do not call this refactor complete until all of the following are true:

- no slug-based model identity remains
- no unsupported provider/model rows are visible in the catalog
- admin model management works without raw JSON editing for normal flows
- settings, stats, RAG, attachments, and agent execution all pass registry integration suites
- backend and frontend test-state docs have been updated for all new test directories

## Canonical References Used For This Plan

- `code_architect/architecture_tree.md`
- `docs/product-specs/settings_hub_spec.md`
- `docs/product-specs/agent_graph_spec.md`
- `docs/product-specs/admin_stats_spec.md`
- `docs/design-docs/platform_current_state.md`
- `backend/documentations/agent_management_state.md`
