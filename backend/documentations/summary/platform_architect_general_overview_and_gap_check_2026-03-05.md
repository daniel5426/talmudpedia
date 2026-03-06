# Platform Architect: General Overview and Gap Check (Chat-Based)

Last Updated: 2026-03-06

## Context
This review uses:
- `backend/documentations/platform_architect_out_of_box_readiness_review.md`
- `backend/documentations/summary/architect_agent_v2_plan.md`
- A real user transcript where the architect repeatedly claimed graph fixes, but agent execution still failed with:
  - `Graph validation failed: Graph must have exactly one Start node (found 0); Graph must have at least one End node`

## Status Update (2026-03-06)
Recent architect hardening addressed core validation/discovery blind spots from this gap check:

- Implemented `agents.nodes.catalog` for node-type discovery from registry-backed operators.
- Implemented `agents.nodes.schema` as bulk-only schema introspection (`node_types[]`).
- Implemented `agents.nodes.validate` (agent-id based) for compile-grade persisted graph validation.
- Replaced prior placeholder `agents.validate` behavior with real compiler validation + tenant-aware runtime reference checks.
- Standardized rich validation payloads (`errors[]`, `warnings[]`, nullable repair fields) for targeted repair loops.
- Added scope-propagation hardening in run/stream to avoid broad default scope injection into `requested_scopes`.
- Improved SDK mutation error surfacing (`details`, `validation_errors`) for better self-repair guidance.

This means G8 is resolved, and G2/G4 have materially improved due to real post-mutation validation signals.

## Current Platform Architect State (What Exists Now)
- Active runtime is Architect V1.1 single-agent loop (not V2 orchestrator).
- Tooling is domain-scoped:
  - `platform-agents` for agent lifecycle/run actions.
  - `platform-rag` for visual RAG pipelines.
  - `platform-assets` and `platform-governance` for other control-plane surfaces.
- Architect prompt and contracts already state:
  - use canonical action IDs,
  - avoid empty graphs,
  - validate after mutations,
  - limited repair loops.

## What Failed in the Transcript
1. Agent graph error was raised (`Start`/`End` missing).
2. Assistant claimed it fixed the issue multiple times.
3. It created RAG pipelines instead of updating the agent graph.
4. Error persisted; user did not see expected nodes on the agent.
5. Later loop degraded into repeated tool invocations and `Max tool iterations reached`.

## Gap Points (Generalized)

### G1. Entity-Type Routing Gap (Agent Graph vs RAG Pipeline)
- Symptom: Assistant executed `rag.*` actions while user asked to fix an agent graph.
- Impact: Creates unrelated resources and increases user confusion.
- Likely cause: Planner/executor does not hard-lock entity target type after parsing user intent.
- Fix direction:
  - Add explicit target lock in run state (`target_kind=agent|pipeline`) after first intent parse.
  - Block cross-entity mutation unless user explicitly switches target.

### G2. No Mandatory Read-After-Write Validation Gate
- Symptom: Assistant declared success after mutation without proving graph invariants.
- Impact: False-positive completion; user trust erosion.
- Likely cause: No enforced post-mutation invariant check in tool policy.
- Fix direction:
  - After `agents.create`/`agents.update`, auto-run `agents.get` + local invariant checks:
    - exactly one `start`,
    - at least one `end`,
    - connectivity from `start` to each `end`.
  - Fail the step if invariants fail; do not emit success language.
- 2026-03-06 status:
  - Improved: compile-grade validation tooling now exists and is exposed to architect (`agents.nodes.validate` + real `agents.validate`).
  - Still recommended: enforce this as a strict mandatory runtime gate policy (not only prompt-level guidance).

### G3. Ambiguous Repair Loop Exit Criteria
- Symptom: repetitive “fixed” claims with no real state convergence.
- Impact: token/tool waste and eventual iteration cap.
- Likely cause: repair loop lacks strong stop/replan rules tied to unchanged error signatures.
- Fix direction:
  - If same validation error repeats twice with no material state diff, stop mutation loop.
  - Return structured blocker report (`attempts`, `last_payload`, `why_not_fixed`, `next_safe_action`).

### G4. Weak “Truth Source” Selection
- Symptom: assistant trusted its own action result text instead of observed agent state.
- Impact: mismatch between narrative and platform reality.
- Likely cause: success condition tied to API 200/create responses, not to state verification.
- Fix direction:
  - Define truth order:
    1) `agents.get` graph state,
    2) `agents.validate` result,
    3) then mutation response metadata.
- 2026-03-06 status:
  - Improved: `agents.validate` is now real compiler output and suitable as truth-source input.
  - Still recommended: explicitly codify precedence in runtime policy/executor checks.

### G5. Missing Agent Graph Patch Helper (Ergonomics)
- Symptom: high friction to safely patch graph nodes/edges; easier to accidentally call unrelated actions.
- Impact: increased operator/model error rate.
- Likely cause: action surface has generic `agents.update` patch, but no narrow graph-safe helper.
- Fix direction:
  - Add helper contract/action pattern:
    - `agents.ensure_minimal_graph_skeleton` (idempotent),
    - or `agents.patch_graph_definition` with strict schema + invariant checks.

### G6. User-Facing Messaging Guardrail Gap
- Symptom: language claimed issue resolved while user observed opposite.
- Impact: severe UX credibility loss.
- Fix direction:
  - Response policy: “success” wording only allowed when post-checks pass.
  - If checks unavailable, response must say “unverified” explicitly.

### G7. Contract-to-Enforcement Drift in Agent Create Path (Confirmed)
- Symptom: agent can be created with only name/slug/description and no graph.
- Impact: draft agents are persisted in non-executable state by default.
- Confirmed evidence:
  - API schema makes `graph_definition` optional on create:
    - `backend/app/api/schemas/agents.py`
  - Service defaults missing graph to empty graph:
    - `backend/app/services/agent_service.py` (`graph_definition=data.graph_definition or {"nodes": [], "edges": []}`)
  - Platform SDK handler does not enforce action payload schema required fields before dispatch:
    - `backend/artifacts/builtin/platform_sdk/handler.py`
- Fix direction:
  - Make create-time graph required at API boundary, or auto-inject minimal valid skeleton server-side.
  - Add payload required-field validation in SDK handler for domain actions.

### G8. Graph Validation Endpoint Is Effectively Stubbed (Confirmed)
- Symptom: tool-driven validation cannot be relied on to catch invalid graph shape.
- Impact: architect loop lacks trustworthy validation signal and can report false success.
- Confirmed evidence:
  - Prior state (2026-03-05): `AgentService.validate_agent` returned placeholder `valid=True`.
- Fix direction:
  - Implement real graph validation with explicit invariant error codes.
  - Use this as mandatory post-mutation gate for architect flows.
- 2026-03-06 status:
  - Resolved: `AgentService.validate_agent` now performs real compile validation and returns structured error/warning payloads.

### G9. Missing First-Class Graph Update Action in Domain Tool Surface (Confirmed)
- Symptom: platform SDK exposes `agents.create/update`, but not explicit graph-only update action.
- Impact: higher chance of malformed patch payloads or no-op updates when model intent is “edit graph”.
- Confirmed evidence:
  - Control SDK has `agents.update_graph(...)`:
    - `backend/talmudpedia_control_sdk/agents.py`
  - Platform SDK handler dispatch table lacks `agents.update_graph`.
    - `backend/artifacts/builtin/platform_sdk/handler.py`
- Fix direction:
  - Add `agents.update_graph` action wrapper and include in architect contracts/examples as preferred repair primitive.

## Immediate Priority Order
1. P0: G2 enforce mandatory read-after-write validation gate in runtime policy.
2. P0: G1 target-kind lock to prevent agent/pipeline cross-mutation drift.
3. P0: G7 contract-enforcement alignment (block/create-valid graph only).
4. P1: G9 expose graph-specific action (`agents.update_graph`) for reliable repair.
5. P1: G3 deterministic repair-loop termination.
6. P1: G6 verified-success-only messaging policy.
7. P2: G5 graph patch helper action(s).
8. P2: G4 codify truth-source precedence in executor logic.

## Suggested Acceptance Checks
- Scenario A: User says “fix this agent graph” with explicit `agent_id`.
  - Expected: only `agents.*` mutation calls; no `rag.*` calls.
- Scenario B: Missing `start`/`end` on agent.
  - Expected: post-update checks fail until graph truly fixed; no premature success response.
- Scenario C: Repeated same validation error.
  - Expected: loop aborts with structured blocker report before max-iteration hard failure.
- Scenario D: Successful repair.
  - Expected: `agents.get` shows valid graph structure and execution no longer throws start/end validation error.

## Notes on Doc Alignment
- No direct contradiction was found between the two referenced docs.
- There is a likely runtime drift risk between documented hardening and deployed behavior seen in transcript; treat this as a verification/deployment parity check item.
