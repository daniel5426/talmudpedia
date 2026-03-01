# Platform Architect Runtime Design (Control Plane SDK, v1)

Last Updated: 2026-03-01

## Status
- Planning/specification only.
- No implementation changes included in this document.

## Context
Current `platform-architect` is seeded as a static GraphSpec v2 staged orchestration with fixed subagents. The target architecture is a real tool-using architect agent that dynamically plans and executes through Control Plane SDK method-backed tools.

## Goals
- Replace fixed stage behavior with adaptive runtime planning/execution.
- Use SDK-method tool actions as the only mutation/execution surface.
- Ensure deterministic contracts, tenant/scope safety, idempotency, and observability.
- Emit machine-readable run report JSON with created/updated resource IDs.

## Non-Goals
- No migration of hosted runtime SDK packages.
- No frontend changes.
- No broad orchestration graph primitive redesign in v1.

## Architecture Decision
### Choice
Single orchestrator agent with optional specialist delegation.

### Why
- Minimizes control complexity while enabling dynamic tool selection and iterative repair.
- Keeps one authoritative planner/executor state machine per run.
- Supports future specialist delegation without reintroducing fixed topology.

### Runtime shape
- `platform-architect` becomes a compact agent graph (`start -> agent -> end`) with tool access.
- Core intelligence is in a deterministic architect runtime tool action (`architect.run`) that executes the planning loop using Control Plane SDK calls.
- Optional future path: delegated specialist subtasks via `agents.start_run` when confidence or complexity thresholds are exceeded.

## Planning and Execution Loop
For each architect run:
1. Intent extraction
- Parse user request into normalized intent object: objectives, constraints, tenant context, mutation policy, success criteria.

2. Capability discovery
- Query SDK-backed catalog/domain read methods to detect existing assets and avoid duplicate creation.

3. Plan generation
- Build explicit action plan with typed steps and idempotency keys.
- Each step declares:
  - `step_id`
  - `action` (`domain.method`)
  - `payload`
  - `idempotency_key`
  - `retry_policy`
  - `success_predicate`

4. Execute
- Execute steps serially or in safe batches.
- Record all tool calls with inputs/outputs/errors and trace metadata.

5. Validate/test
- Validate agent and pipeline via SDK methods (`agents.validate`, pipeline compile checks, optional smoke execution).

6. Repair/replan
- On retryable/transient errors, retry by policy.
- On deterministic validation failures, generate patch plan and re-execute bounded repair iterations.

7. Stop
- Success when all mandatory predicates pass.
- Stop with explicit reason when max attempts reached or blocked by approvals/scope policy.

## Tooling Surface (Exact SDK Method Groups)
Architect runtime tool action set (invoked through platform SDK tool wrappers):
- `catalog.*`
- `agents.*`
- `rag.*`
- `tools.*`
- `artifacts.*`
- `models.*`
- `credentials.*`
- `knowledge_stores.*`
- `workload_security.*`
- `auth.*`
- `orchestration.*` (feature-gated, optional)

### Tool schema strategy
- Canonical action id: `domain.method` only.
- Typed payload per action with `additionalProperties: false` for architect-owned orchestration payloads.
- Unified envelope fields:
  - `action`
  - `payload`
  - `dry_run`
  - `validate_only`
  - `idempotency_key`
  - `request_metadata` (`trace_id`, `reason`, `source=agent-tool`)

## Safety and Governance
### Scope boundaries
- Tenant must be explicit for every mutating operation.
- No fallback to implicit tenant selection.
- Scope checks enforced pre-dispatch.

### Approval-sensitive mutations
- Mutations that require approval return structured block status:
  - `status=blocked_approval`
  - `required_approval`
  - `approval_subject`
- Architect stops mutation path and reports unblock action.

### Idempotency and safe mutation pattern
- Every mutation uses deterministic idempotency key:
  - `architect:{run_id}:{step_id}:{intent_hash}`
- Read-before-write preferred for `create_or_update` semantics.
- Existing matching assets are reused and recorded as `reused=true`.

### Dry-run
- Full plan simulation path with real validation/auth checks and no persistence.
- Report includes predicted writes and blocked steps.

## State Model
Persisted and in-memory run state:
- `intent`
- `constraints`
- `plan` (steps with status)
- `attempt_counters`
- `tool_call_log`
- `decision_log`
- `resource_registry`:
  - `agents[]`
  - `rag_pipelines[]`
  - `artifacts[]`
  - `tools[]`
  - `jobs[]`
- `validation_results`
- `final_status`

Resource registry entry shape:
- `kind`
- `id`
- `slug`
- `operation` (`created|updated|reused|failed`)
- `idempotency_key`
- `trace_id`

## Machine-Readable Run Report JSON
```json
{
  "run_id": "string",
  "tenant_id": "string",
  "status": "success|partial_success|failed|blocked_approval",
  "objective": "string",
  "summary": "string",
  "plan": {
    "total_steps": 0,
    "completed_steps": 0,
    "failed_steps": 0,
    "repaired_steps": 0
  },
  "resources": {
    "agents": [],
    "rag_pipelines": [],
    "artifacts": [],
    "tools": []
  },
  "validation": {
    "agent_validation": [],
    "pipeline_validation": [],
    "tests": []
  },
  "observability": {
    "trace_id": "string",
    "tool_calls": [],
    "decision_events": []
  },
  "failures": [],
  "next_actions": []
}
```

## Minimal Vertical Slice Spec (Phase MVP)
Input: one user request to create capability assets.

Expected behavior:
1. Create or update one RAG visual pipeline via `rag.create_or_update_pipeline`.
2. Compile pipeline via `rag.compile_pipeline`.
3. Create or update one agent via `agents.create_or_update` referencing target graph/tooling.
4. Validate agent via `agents.validate`.
5. Emit run report JSON with created IDs and tool call trace.
6. On one controlled failure (example: compile fails), apply one repair patch and retry compile once.

Stop conditions:
- Success after validations pass.
- Fail with clear non-retryable reason.
- Block with explicit approval requirement.

## Phased Implementation Plan
### Phase 1: Runtime contracts and planner state
- Add architect runtime action contract and schemas.
- Add internal planning state model and report model.
- Add deterministic idempotency strategy utility.

### Phase 2: SDK-backed execution engine
- Implement action executor for `agents.*` and `rag.*` minimal path.
- Add retry taxonomy (retryable vs non-retryable).
- Add observability event emission per decision/tool call.

### Phase 3: Seed new architect path
- Seed `platform-architect` as single dynamic tool-using agent (no fixed staged graph).
- Attach only required tools and enforce explicit action contracts.
- Keep legacy path behind temporary fallback flag during migration window.

### Phase 4: Validation and repair loop
- Add compile/validate/test checks and repair planner.
- Add stop conditions and blocked-approval handling.

### Phase 5: Hardening
- Add tenant/scope abuse tests.
- Add deterministic replay test with fixed idempotency keys.
- Add audit/report contract snapshots.

## Test Plan (for implementation phase)
Feature test directory: `backend/tests/platform_architect_runtime/`

Required tests:
- Happy path:
  - Creates one pipeline and one agent through SDK wrappers.
  - Validates both and returns `status=success` with IDs in report.
- Recovery path:
  - First compile fails with retryable/validation error.
  - Architect applies repair patch and second compile succeeds.
  - Report includes failure event and repair event.

Additional recommended tests:
- Approval-blocked mutation path.
- Dry-run no persistence path.
- Tenant mismatch rejection.

## Migration Notes
- New architect path should be default for new runs once validated.
- Legacy staged graph may remain temporarily behind a feature flag as rollback only.
- Remove legacy path after parity and soak window completion.

## Documentation Contradiction Detected
There is a mismatch between docs and runtime surface:
- `backend/documentations/platform_control_plane_sdk_spec_v1.md` section 12.2 still lists a narrow legacy action baseline.
- Current runtime handler already supports broad canonical `domain.action` dispatch.

This should be reconciled during implementation to avoid contract confusion.
