# Platform Architect Out-of-Box Readiness Review

Last Updated: 2026-03-02

## Scope
Review of current Platform Architect V1 runtime reliability for creating draft agents and RAG pipelines with minimal user hand-holding.

## Primary Findings
1. `rag.create_visual_pipeline` contract drift:
- Architect/domain contracts and examples used `graph_definition` + `slug`.
- Actual REST create endpoint consumes top-level `nodes`/`edges` and does not consume `graph_definition`.
- Effect: architect-created pipelines can be persisted as empty even when `graph_definition` is provided.

2. Missing-action failure surfaced as raw artifact validation exception:
- Platform SDK artifact manifest required `action` at artifact input-validation layer.
- If model emitted malformed tool args, run failed early with `Artifact input validation failed: Required field 'action' is missing or null`.
- This bypassed the handler's structured `MISSING_REQUIRED_FIELD` error envelope and reduced repairability.

3. Tenant context mismatch in RAG router:
- Architect/tool runtime standardizes on explicit `tenant_id`.
- Several RAG flows still relied on `tenant_slug`/membership lookup behavior.
- Effect: intermittent permission denials for valid user-principal tokens without `tenant_slug`.

4. Empty draft guidance in action examples:
- Seeded examples for agent/pipeline creation used empty graphs (`nodes: [], edges: []`).
- This reinforced non-functional draft creation behavior.

## Implemented Hardening (This Change Set)
1. RAG payload normalization in platform SDK action wrappers:
- `graph_definition -> nodes/edges` mapping for create/update actions.
- Control-plane meta fields stripped from request bodies.
- File: `backend/artifacts/builtin/platform_sdk/actions/rag.py`.

2. Structured missing-action path preserved for platform SDK tool calls:
- Disabled pre-handler strict artifact input enforcement specifically for `builtin/platform_sdk` invocations through tool executor.
- This allows handler-level structured validation errors to flow back to the architect loop.
- File: `backend/app/agent/executors/tool.py`.

3. RAG tenant resolution alignment:
- RAG router context now accepts principal `tenant_id` without requiring `tenant_slug`.
- Non-admin user fallback uses first membership tenant when `tenant_slug` is omitted.
- File: `backend/app/api/routers/rag_pipelines.py`.

4. Architect contract guidance updates:
- `rag.create_visual_pipeline` action schema/examples now center on top-level `nodes`/`edges`.
- Agent and pipeline examples now show non-empty starter skeletons.
- Prompt instructions explicitly prohibit empty graph drafts.
- File: `backend/app/services/platform_architect_contracts.py`.

5. Added parity coverage for graph normalization:
- Tests verify create/update wrapper translation from `graph_definition` to `nodes`/`edges`.
- File: `backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py`.

## Forward Plan (Recommended)
1. Contract unification:
- Remove residual `graph_definition` usage from architect-facing RAG contracts after migration window.
- Keep wrapper compatibility only as temporary bridge.

2. Starter templates as first-class artifacts:
- Add explicit starter templates for:
  - generic assistant agent,
  - retrieval-enabled QA agent,
  - ingestion pipeline,
  - retrieval pipeline.
- Architect should default to templates and patch, not synthesize from empty graphs.

3. Permission model normalization:
- Eliminate `tenant_slug` requirements from control-plane endpoints where possible.
- Keep SDK surface uniformly `tenant_id`-driven.

4. Runtime repair ergonomics:
- Add machine-readable error hints in handler for missing `action` with canonical examples per tool slug.
- Add retry guardrails for malformed tool-call arguments before consuming repair loops.

5. End-to-end integration verification:
- Add DB-backed integration tests that run seeded `platform-architect` against real routers for:
  - create/compile pipeline,
  - create/validate agent,
  - deterministic repair path,
  - tenant/scope-denied path.

## Risk Notes
- Backward-compatibility shim (`graph_definition`) should be time-boxed; retaining it indefinitely reintroduces contract ambiguity.
- Membership fallback behavior improves UX but should be audited for multi-tenant explicitness expectations in admin tooling.
