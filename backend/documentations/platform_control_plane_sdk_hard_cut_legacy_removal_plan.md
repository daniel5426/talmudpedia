# Platform Control Plane SDK Hard-Cut Legacy Removal Plan

Last Updated: 2026-03-01

## Purpose
This document defines the **hard-cut deletion plan** for legacy control-plane SDK and tooling paths.

Hard-cut means:
- No compatibility fallback paths.
- No dual-write or dual-route behavior.
- No silent default actions that mask bad calls.
- Callers must use the new canonical Control Plane SDK v1 contract.

Reference contract:
- `backend/documentations/platform_control_plane_sdk_spec_v1.md`

## Scope
In scope:
- Backend control-plane SDK client code and tool adapters.
- Control-plane API route compatibility aliases.
- Architect tool behavior that emulates legacy planner behavior.
- Docs/tests that encode fallback behavior for these surfaces.

Out of scope:
- Non-control-plane app fallbacks (published apps runtime, voice, text, etc.).
- Model policy fallback semantics unrelated to SDK transport/contracts.

## Hard-Cut Rules (Non-Negotiable)
1. Any call to deprecated control-plane routes fails immediately with a structured error.
2. Any call without explicit action/method fails validation (no inferred action).
3. No route fallback chains (for example `/agents` then `/api/agents`).
4. No implicit tenant fallback (`first tenant`) in SDK code paths.
5. SDK/tool contracts must be identical JSON schemas for each domain action.

## Legacy Surfaces To Delete

### A) Legacy Lightweight SDK Package (Delete Entirely)
Delete after new SDK packages are live and parity-tested.

- `backend/sdk/client.py`
- `backend/sdk/pipeline.py`
- `backend/sdk/nodes.py`
- `backend/sdk/artifacts.py`
- `backend/sdk/graph_builder.py`
- `backend/sdk/validators.py`
- `backend/sdk/fuzzer.py`
- `backend/sdk/README.md`
- `backend/sdk/__init__.py`

Why legacy:
- Catalog-first dynamic builder, not canonical typed contract SDK.
- Contains old agent create path usage (`/api/agents`) in `pipeline.py`.

Hard-cut replacement:
- `talmudpedia_control_sdk` (Python)
- `@talmudpedia/control-sdk` (TypeScript)

### B) Platform SDK Tool Legacy Behaviors (Delete from artifact handler)
File:
- `backend/artifacts/builtin/platform_sdk/handler.py`

Delete these behaviors:
- Route fallback logic for deploy-agent:
  - primary `/agents` + fallback `/api/agents`.
- Planner-centric coarse action multiplexing as primary integration surface (`validate_plan` / `execute_plan`) once domain-method wrappers are in place.
- Legacy default action assumptions in auth scope resolution (`action or "fetch_catalog"`).
- “Unknown action” branch that keeps large compatibility action list instead of strict method registry.

Hard-cut replacement:
- Generated/typed tool wrappers mapped 1:1 to SDK module methods.

### C) Executor Auto-Defaulting for Platform SDK Tool (Delete)
File:
- `backend/app/agent/executors/standard.py`

Delete logic that auto-injects Platform SDK action on empty tool input:
- Default to `{ "action": "fetch_catalog" }`
- Second-pass forced `{ "action": "respond" }`

Why:
- Masks upstream planner/tool-call errors.
- Violates hard-cut explicit-contract behavior.

Hard-cut replacement:
- Empty or malformed call returns structured validation error.

### D) Deprecated/Conflicting Agent Route Compatibility
Delete compatibility assumptions and route aliases around legacy agents pathing.

Route target:
- Remove support for legacy `/api/agents` in SDK/tool flows.

Code paths currently tied to this legacy behavior:
- `backend/sdk/pipeline.py`
- `backend/artifacts/builtin/platform_sdk/handler.py`

Hard-cut policy:
- Canonical create/update/execute path is `/agents/*` only.

### E) Duplicate Operator Catalog Route Surface (Consolidate by Deletion)
Current duplicate exposure of `GET /agents/operators` from:
- `backend/app/api/routers/agents.py`
- `backend/app/api/routers/agent_operators.py`

Hard-cut action:
- Keep exactly one authoritative router implementation.
- Delete the duplicate route registration to prevent drift.

### F) Legacy Docs That Must Be Removed or Archived
- `backend/documentations/sdk_specification.md`

Reason:
- This older doc reflects the previous lightweight SDK architecture and can drift against v1 contract.

Hard-cut replacement:
- Keep only `platform_control_plane_sdk_spec_v1.md` as canonical SDK contract doc.

## Legacy Tests To Delete/Rewrite

### Delete tests that explicitly assert fallback behavior
Candidates:
- Any tests asserting `/api/agents` fallback from Platform SDK handler.
- Any tests asserting empty-action defaulting (`fetch_catalog`/`respond`) in executor path.

### Rewrite to strict-contract tests
Required test behavior:
- Missing action => validation error.
- Deprecated route => explicit error.
- SDK method input schema == tool action input schema.
- Dry-run/idempotency semantics preserved with no fallback branching.

## API Hard-Cut Changes

### 1) Endpoint removal (caller-visible)
- Remove deprecated `/api/agents` control-plane usage.

Expected response if called post-cut:
- `410 Gone` or `404 Not Found` with error code `DEPRECATED_ENDPOINT`.

### 2) Tenant handling normalization
- Remove all SDK reliance on server side first-tenant fallback.
- SDK must send explicit tenant context (`X-Tenant-ID` or method-typed tenant identifier).

### 3) Knowledge stores consistency
- Use backend-defined update method only:
  - `PATCH /admin/knowledge-stores/{store_id}`
- Remove client implementations using `PUT` for this endpoint.

## Frontend Service Legacy Cleanup (Control Plane Only)
Once TS control SDK is adopted by frontend services, remove per-service custom transport quirks from:
- `frontend-reshet/src/services/*` (control-plane related modules)

Hard-cut target:
- UI uses generated/typed SDK client calls directly.
- No endpoint-specific patching in each service file.

## Deletion Order (Hard-Cut Sequence)
1. Ship new Python + TS Control SDK with full module coverage.
2. Replace Platform SDK artifact internals with SDK-method tool wrappers.
3. Remove executor auto-defaulting behavior.
4. Remove `/api/agents` compatibility usage from all callers.
5. Remove `backend/sdk/` package.
6. Remove duplicate `/agents/operators` route implementation.
7. Remove/archive legacy SDK docs and fallback-based tests.

## Exit Criteria (Definition of Done)
All conditions must be true:
1. No references to `/api/agents` in SDK/tool code paths.
2. No Platform SDK tool call succeeds without explicit method/action.
3. No control-plane SDK call depends on first-tenant fallback behavior.
4. All control-plane mutations support idempotency key + dry-run in SDK API.
5. Contract parity tests pass for UI vs SDK vs tool wrappers.
6. Legacy `backend/sdk/` package is deleted from repository.
7. `sdk_specification.md` is removed or clearly archived as non-canonical.

## Risks and Mitigations
- Risk: hidden callers still use legacy SDK paths.
  - Mitigation: add temporary telemetry on deprecated endpoints before removal window, then hard remove.
- Risk: agent plans still emit coarse legacy actions.
  - Mitigation: enforce strict tool schema validation + fail fast.
- Risk: drift between router schemas and SDK types.
  - Mitigation: generate SDK types from shared versioned contract schemas.

## Immediate Cleanup Backlog (Actionable)
1. Delete old `backend/sdk/` package once replacement SDK is merged.
2. Expand parity coverage from currently migrated platform actions to the full SDK method surface.
3. Add CI-level wired step that always runs the `/api/agents` guardrail test.

## Implementation Progress (2026-03-01)
Completed:
1. Removed `/agents -> /api/agents` fallback branch from `backend/artifacts/builtin/platform_sdk/handler.py` (`_step_deploy_agent` now uses canonical `/agents` path only).
2. Removed Platform SDK empty-call auto-defaulting from `backend/app/agent/executors/standard.py` (`fetch_catalog` / `respond` synthetic defaults removed).
3. Consolidated duplicate `GET /agents/operators` exposure by removing `agent_operators` router registration from `backend/main.py`.
4. Updated legacy lightweight SDK agent create route in `backend/sdk/pipeline.py` from `/api/agents` to `/agents`.
5. Added/updated strict-contract tests:
   - `backend/tests/platform_sdk_tool/test_platform_sdk_actions.py`
   - `backend/tests/workload_delegation_auth/test_platform_sdk_delegated_auth_flow.py`
6. Expanded Python replacement SDK coverage in `backend/talmudpedia_control_sdk/` to include:
   - `catalog`, `rag`, `models`, `credentials`, `knowledge_stores`, `workload_security`, `auth`, `orchestration`
   - plus additional contract tests in `backend/tests/control_plane_sdk/test_additional_modules.py`.
7. Added shared client config capabilities required for external consumers:
   - dynamic tenant resolution (`tenant_resolver`)
   - env-based client bootstrap (`ControlPlaneClient.from_env(...)`)
   - validation tests added in `backend/tests/control_plane_sdk/test_client_and_modules.py`.
8. Added env-gated HTTP integration smoke tests for SDK module surfaces in
   `backend/tests/control_plane_sdk/test_http_integration.py`.
9. Removed planner-centric coarse platform actions from runtime dispatch:
   - `validate_plan`
   - `execute_plan`
10. Migrated platform SDK action dispatch to canonical domain-method wrappers with action alias normalization to canonical dotted IDs.
11. Routed runtime orchestration actions through `talmudpedia_control_sdk.orchestration.*` method wrappers.
12. Added parity test coverage for tool action-to-SDK method contract behavior in:
    - `backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py`
13. Added guardrail test to fail on `/api/agents` usage in control-plane SDK/tool Python paths:
    - `backend/tests/control_plane_sdk/test_no_legacy_api_agents_refs.py`
14. Archived `backend/documentations/sdk_specification.md` as non-canonical legacy context.

In progress:
1. Replacement SDK implementation is underway via `backend/talmudpedia_control_sdk/` (full module surface exists; platform handler runtime dispatch now uses domain-method wrappers, but full surface parity rollout is still incomplete).

Pending:
1. Delete legacy `backend/sdk/` package after full replacement and parity validation.
2. Expand parity tests to cover all required canonical actions in the v1 spec appendix.
3. Wire the `/api/agents` guardrail test into always-on CI execution path.

## Contradictions Requiring Resolution
1. Existing tests/docs in workload delegation area may still describe fallback auth behavior not present in current handler implementation.
