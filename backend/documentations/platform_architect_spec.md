# Platform Architect Spec

Last Updated: 2026-03-12

## Purpose
This is the single authoritative spec for the Platform Architect.
Use this file as the source of truth for current runtime behavior, active constraints, known gaps, and next-step design direction.

## Scope
`platform-architect` is the backend platform-building agent responsible for drafting and repairing agents, RAG pipelines, tools, artifacts, and related platform assets through internal domain-scoped tools.

This spec covers:
- the current live V1.2 runtime
- control-plane/tooling boundaries
- safety and mutation rules
- active gaps and acceptance criteria
- test coverage and E2E harness references
- future V2 direction

## Current State (Source of Truth)

### Runtime classification
- Active runtime is Architect V1.2.
- It is a single tool-using runtime agent.
- It is not the old staged GraphSpec v2 orchestrator.
- There is no active `architect.run` runtime path.

### Seeded graph shape
- `start -> architect_runtime(agent node) -> end`
- Core behavior lives in the `architect_runtime` prompt/instructions and attached domain tools.
- Architect output is plain text; there is no architect-specific forced JSON output format.

### Seeding and bootstrapping
Relevant startup seed flow:
1. `seed_platform_sdk_tool(db)`
2. `seed_platform_architect_agent(db)`

Architect seeding:
- seeds four domain-scoped tools
  - `platform-rag`
  - `platform-agents`
  - `platform-assets`
  - `platform-governance`
- upserts a tenant-scoped `platform-architect` agent with those four tools attached

Primary implementation files:
- `backend/app/services/registry_seeding.py`
- `backend/app/services/platform_architect_contracts.py`

Seeded runtime defaults:
- `architect_runtime.config.temperature = 1`
- `architect_runtime.config.reasoning_effort = medium`

Shared model fallback:
- backend runtime normalizes `temperature` to `1` for OpenAI/Azure model families that only accept `1` today (`gpt-5*`, `o1*`, `o3*`, `o4*`)
- this normalization is shared at the LLM provider layer and is not architect-specific

### Runtime loop
The architect runtime follows this direct loop:
1. Extract intent and constraints.
2. Build an explicit step plan in context.
3. Execute one domain tool call at a time.
4. Prefer semantic graph helpers for graph edits, then schema-aware patch actions when needed.
5. Validate after each mutation.
6. Allow a limited repair budget for malformed but potentially self-correctable platform-tool calls.
7. Stop on repeated identical mutation failures with a blocker report instead of looping indefinitely.
8. Return a normal text response.

### Node intelligence and validation
The architect can discover and validate agent graph structure through `platform-agents`:
- `agents.nodes.catalog`
- `agents.nodes.schema`
- `agents.nodes.validate`
- `agents.validate`

Validation is compile-grade and returns structured `errors[]` and `warnings[]`.

The architect can discover RAG operator contracts through `platform-rag`:
- `rag.operators.catalog`
- `rag.operators.schema`

RAG discovery must not use `agents.nodes.*`.
`rag.operators.schema` should be treated as the source of truth for:
- operator config fields
- runtime-bindable config value shapes
- exact visual pipeline node wrapper shape
- shared create-pipeline edge/top-level contract hints

## Domain Tool Surface

### Tool boundaries
- `platform-rag` -> `rag.*`
- `platform-agents` -> `agents.*`
- `platform-assets` -> `tools.*`, `artifacts.*`, `models.*`, `credentials.*`, `knowledge_stores.*`
- `platform-governance` -> `auth.*`, `workload_security.*`, `orchestration.*`

Cross-domain action usage through the wrong domain tool is denied with `SCOPE_DENIED`.

### Action contract model
Each domain tool exposes:
- top-level `action`
- top-level `payload`
- action-specific payload schemas through `oneOf`
- `x-action-contract` hints for summary, required fields, examples, and failure codes

Current architect-facing policy:
- architect should use canonical action ids only
- architect must send only canonical top-level `action` / `payload` tool input
- architect should not ask the user for mutation metadata that runtime can derive
- architect should prefer graph helper actions before generic graph patch actions
- architect should validate after mutations instead of claiming success from mutation responses alone
- architect should use `agents.nodes.*` only for agent graphs and `rag.operators.*` only for RAG pipelines

## Safety, Auth, and Mutation Rules

### Tenant handling
- Architect runtime is tenant-bound.
- Runtime tenant context is authoritative for architect-issued mutations.
- Architect should not ask the user for `tenant_id`.
- If runtime tenant context exists, payload attempts to override `tenant_id` are rejected with `TENANT_MISMATCH`.
- If no effective tenant context exists for a mutation, runtime returns `TENANT_REQUIRED`.

### Idempotency and request metadata
- Architect should not block on asking the user for `idempotency_key` or `request_metadata`.
- Mutation idempotency and request metadata may be synthesized by runtime/control-plane layers when absent.

### Draft-first policy
- `agents.publish`, `tools.publish`, and `artifacts.publish` are blocked unless explicit publish intent is set.
- Publish intent flag: `objective_flags.allow_publish=true`
- Policy denial code: `DRAFT_FIRST_POLICY_DENIED`

### Approval-sensitive actions
- Approval-sensitive SDK failures normalize to:
  - `result.status = blocked_approval`
  - error code `SENSITIVE_ACTION_APPROVAL_REQUIRED`
  - actionable `next_actions`

### Scope propagation
- Broad caller scopes are no longer auto-injected into `requested_scopes` by default.
- Delegated chains with `grant_id` still propagate requested scopes explicitly.

## Tool Input and Error Handling

### Current handler behavior
Platform SDK handler behavior now supports:
- canonical top-level `action` / `payload` dispatch only
- explicit contract failures when callers send wrapped tool input in `value` / `query` / `text`
- wrapped-input failures now preserve `attempted_action`, wrapper source field, and whether the embedded payload was parseable JSON
- structured mutation errors that preserve backend validation details

### Important practical constraint
There is no wrapped-input recovery path anymore.
Platform SDK callers must send a structured top-level tool input object directly.

### Repair budget behavior
- `NON_CANONICAL_PLATFORM_SDK_INPUT` is treated as repairable, not terminal on first sight
- current retry budget is three repair attempts, then block on the fourth matching failure
- blocker attribution now prefers the embedded attempted action over `noop` when wrapped input is rejected

### Structured error expectations
Important architect-visible error categories:
- `MISSING_REQUIRED_FIELD`
- `NON_CANONICAL_PLATFORM_SDK_INPUT`
- `SCOPE_DENIED`
- `TENANT_REQUIRED`
- `TENANT_MISMATCH`
- `DRAFT_FIRST_POLICY_DENIED`
- `SENSITIVE_ACTION_APPROVAL_REQUIRED`
- `VALIDATION_ERROR`

Agent mutation failures should preserve structured backend validation details through:
- `details`
- `validation_errors`

RAG pipeline creation failures should preserve field-level backend validation details through:
- `details`
- `validation_errors`

## Current Known Gaps

### P0 gaps
1. Target-kind lock is still not enforced strongly enough.
- If user intent is “fix an agent,” architect should not drift into `rag.*` mutations.

2. Truth-source precedence should be codified more strictly in final user messaging.
- Prefer observed state and validation over mutation response narratives.

### P1 gaps
3. User-facing success language still needs hard gating.
- “fixed” should only be emitted after post-checks pass.

### P1/P2 ergonomics gaps
4. Graph mutation helper coverage can still expand.
- The current helper set covers common agent and RAG edits but not every high-frequency mutation intent yet.

5. RAG creation still uses `rag.create_visual_pipeline`.
- This is acceptable in V1.2, but architect reliability depends on catalog/schema discovery before create.

## Testing and Verification

### Focused runtime tests
Feature directory:
- `backend/tests/platform_architect_runtime/`

Current coverage includes:
- direct domain-tool happy path
- repair path
- approval-blocked path
- tenant/scope denial paths
- replay idempotency
- tenant-binding hardening
- architect seed assertions
- no forced JSON output in architect config/prompt

### Platform SDK tool tests relevant to architect
Feature directory:
- `backend/tests/platform_sdk_tool/`

Relevant coverage includes:
- strict rejection of wrapped `value` / `query` / `text` tool input
- preservation of wrapped attempted action and parseability metadata on non-canonical failures
- canonical action dispatch and alias normalization
- parity coverage for `agents.graph.*` and `rag.graph.*` actions

## Execution Tracing

Runtime execution events are persisted through the shared execution trace recorder at `backend/app/agent/execution/trace_recorder.py`.

For architect diagnosis, the most relevant events are now:
- `reasoning.tool_call_inferred`
  - emitted when the reasoning node infers a tool call from assistant JSON fallback instead of a native provider tool call
  - includes the raw inferred payload, normalized tool call, wrapped input keys, and whether a top-level action was present
- `tool.execution_prepared`
  - emitted immediately before tool execution
  - includes tool slug, implementation type, input shape, and sanitized input preview
- `platform_sdk_local.dispatch_prepared`
  - emitted by the local architect platform-tool dispatcher
  - includes the sanitized payload preview and runtime context preview sent to the Platform SDK handler
  - non-serializable runtime objects such as callables are stringified before persistence (for example `<callable:mint_token>`)
- `platform_sdk_local.dispatch_completed`
  - emitted after the Platform SDK handler returns
  - includes a sanitized result preview
- `tool.execution_completed`
  - emitted after tool execution and guardrail processing
  - includes tool slug, implementation type, and sanitized output preview
- `architect.repair_attempted`
  - emitted when a repeated architect mutation failure is recorded
  - includes normalized failure code, attempt count, fingerprint, and target resource
- `architect.repair_blocked`
  - emitted when retry budget is exhausted and the architect is blocked

### Investigated live failure mode
The investigated live architect failure on 2026-03-12 was not caused by the local `platform_sdk` dispatcher. Persisted run traces showed that the malformed payload already existed at `on_tool_start`: the architect emitted top-level `query` and `value` fields containing a malformed stringified `{"action":"agents.create","payload":...}` blob. The strict Platform SDK handler correctly rejected that as `NON_CANONICAL_PLATFORM_SDK_INPUT`. The new trace events above are intended to make that exact distinction immediately visible in future runs.

### Live E2E harness
Harness directory:
- `backend/tests/platform_architect_e2e/`

Behavior:
- resolves seeded `platform-architect` by slug
- runs one live scenario per documented domain action
- validates outcomes through run evidence, control-plane checks, and DB linkage checks
- persists report at `backend/artifacts/e2e/platform_architect/latest_report.json` by default

## Execution Logging

### Goal
- Every architect run should leave behind a chronological execution log that can be inspected after the fact when a bug is reported.

### Current mechanism
- Runtime execution events are persisted through the shared execution trace recorder at `backend/app/agent/execution/trace_recorder.py`.
- Events are recorded in `agent_traces` in sequence order instead of only keeping a partial start/end span view.
- Tool calls now get a dedicated `tool_call_id`, so repeated calls from the same node remain distinguishable in the trace log.
- Architect runs also emit lifecycle markers for setup, graph compilation, adapter readiness, stream start, and terminal status.

### Retrieval
- API: `GET /agents/runs/{run_id}/events`
- Response includes ordered events with `sequence`, `timestamp`, `event`, `span_id`, `visibility`, and full event payload.
- Optional mirrored JSONL file logging is available through:
  - `AGENT_EXECUTION_EVENT_LOG_ENABLED`
  - `AGENT_EXECUTION_EVENT_LOG_FILE`

### Reuse expectation
- This mechanism is shared execution infrastructure, not architect-specific glue.
- Other agent-style runtimes should emit through the same recorder instead of creating custom ad-hoc debug logs.

## Acceptance Criteria For Ongoing Work
When iterating on Platform Architect, these checks should remain true:

1. If the user asks to fix an agent graph, only `agents.*` mutations should be used unless the user explicitly changes target type.
2. Architect should validate state after each mutation and should not claim success before validation passes.
3. Tenant scope must remain runtime-bound and non-overridable by model payload.
4. Wrapped tool input should fail fast with `NON_CANONICAL_PLATFORM_SDK_INPUT`.
5. Architect prompt/config should stay plain-text oriented; no forced architect-only JSON response contract.
6. Every architect run should expose an ordered execution-event log that is sufficient to reconstruct tool calls, lifecycle phases, and terminal failure context.
7. Repeated identical graph mutation failures should stop the run with `architect.repair_blocked` / `architect.progress_stalled` events.
8. Unsupported RAG actions and non-canonical Platform SDK input should not cause architect retry loops.

## Future Direction (V2)

### Status
V2 remains future-state planning, not the active production path.

### Direction
Potential V2 evolution:
- orchestrator + specialist sub-agents
- API-only execution
- draft-only creation by default
- delegated workload identity for privileged internal actions
- stronger multi-case testing before reporting success

### Constraint
V2 should build on the current direct domain-action contracts and runtime safety model, not reintroduce legacy `architect.run` behavior.

## Related Files

### Primary implementation
- `backend/app/services/platform_architect_contracts.py`
- `backend/app/services/registry_seeding.py`
- `backend/app/services/platform_architect_guardrails.py`
- `backend/app/services/graph_mutation_service.py`
- `backend/app/services/agent_graph_mutation_service.py`
- `backend/app/services/rag_graph_mutation_service.py`
- `backend/artifacts/builtin/platform_sdk/handler.py`
- `backend/artifacts/builtin/platform_sdk/actions/agents.py`
- `backend/artifacts/builtin/platform_sdk/actions/rag.py`

### Test coverage
- `backend/tests/platform_architect_runtime/`
- `backend/tests/platform_sdk_tool/`
- `backend/tests/platform_architect_e2e/`

## Historical Note
The older standalone Platform Architect markdown docs were removed after consolidation on 2026-03-07.
This file is now the only architect-owned markdown spec that should be edited for current work.
