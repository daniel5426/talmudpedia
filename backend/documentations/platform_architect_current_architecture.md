# Platform Architect Current Architecture

Last Updated: 2026-03-06

## Scope
This document describes the current Platform Architect runtime after the V1.1 hard cut to direct multi-tool execution.

## High-Level Classification
`platform-architect` is now a **single tool-using runtime agent**.
It is no longer a staged GraphSpec v2 orchestrator and no longer routes through `architect.run`.

## Seeding and Bootstrapping
Startup seed flow relevant to architect:
1. `seed_platform_sdk_tool(db)`
2. `seed_platform_architect_agent(db)`

Inside architect seeding:
- Seeds domain-scoped control-plane tools:
  - `platform-rag`
  - `platform-agents`
  - `platform-assets`
  - `platform-governance`
- Each domain tool now has strict action contracts:
  - top-level `action` enum
  - strict action-specific `payload` via `oneOf`
  - `x-action-contract` hints per action (summary, required fields, example payload, failure codes)
  - mutating actions require `tenant_id`, `idempotency_key`, and `request_metadata`
- Upserts tenant `platform-architect` agent with all four domain tools attached.

Primary source:
- `backend/app/services/registry_seeding.py`
- `backend/app/services/platform_architect_contracts.py`

## Agent Graph Shape
`platform-architect` graph is minimal:
- `start -> architect_runtime(agent node) -> end`

The architect node prompt now enforces a direct loop:
1. Extract intent and constraints.
2. Build explicit plan in context.
3. Execute one domain tool call at a time.
4. Validate after each mutation.
5. Repair/replan with max two loops.
6. Return a normal text response; no architect-specific JSON output format is enforced.

## Runtime Execution Model
Execution is dynamic via canonical domain actions in the Platform SDK handler.
There is no architect-meta runtime path.

Node intelligence actions are now part of the `platform-agents` surface:
- `agents.nodes.catalog`
- `agents.nodes.schema` (bulk `node_types[]`)
- `agents.nodes.validate` (agent-id based persisted draft validation)

Primary source:
- `backend/artifacts/builtin/platform_sdk/handler.py`

## Domain Tool Boundaries
Tool/action boundaries are enforced by tool slug prefix policy:
- `platform-rag` -> `rag.*`
- `platform-agents` -> `agents.*`
- `platform-assets` -> `tools.*`, `artifacts.*`, `models.*`, `credentials.*`, `knowledge_stores.*`
- `platform-governance` -> `auth.*`, `workload_security.*`, `orchestration.*`

Cross-domain action use via the wrong tool returns `SCOPE_DENIED`.

## Runtime Safety and Policy
- Tenant context is required before mutating actions (`TENANT_REQUIRED` on violation).
- Runtime tenant context is now authoritative for architect-issued mutations:
  - the architect prompt/contracts no longer require asking the user for `tenant_id`, `idempotency_key`, or `request_metadata`
  - if runtime tenant context exists, payload attempts to override `tenant_id` are rejected with `TENANT_MISMATCH`
  - mutation idempotency and request metadata may be synthesized from runtime/control-plane layers when absent
- Draft-first is hard policy:
  - `agents.publish`, `tools.publish`, and `artifacts.promote` are blocked unless explicit publish intent is set (`objective_flags.allow_publish=true`).
  - Policy denial returns `DRAFT_FIRST_POLICY_DENIED`.
- Approval-sensitive SDK failures are normalized into:
  - `result.status = blocked_approval`
  - error code `SENSITIVE_ACTION_APPROVAL_REQUIRED`
  - actionable `next_actions`.
- Run/stream scope propagation was hardened:
  - router no longer auto-injects broad caller scopes into `requested_scopes` by default.
  - delegated chains (`grant_id` present) still propagate requested scopes explicitly.

## Output Contract
Domain tool output envelope is standardized:
- `result`
- `errors`
- `action`
- `dry_run`
- `meta`:
  - `trace_id`
  - `request_id`
  - `idempotency_key`
  - `idempotency_provided`
  - `tool_slug`

Architect run report contract (returned by the seeded architect node) remains machine-readable with:
- `run_id`, `tenant_id`, `status`, `objective`, `summary`
- plan counters
- resources (`agents`, `rag_pipelines`, `artifacts`, `tools`)
- validation evidence
- observability (`trace_id`, `tool_calls`, `decision_events`)
- `failures`, `next_actions`

`agents.nodes.validate` and `agents.validate` now return structured validation payloads:
- `valid`
- `errors[]` with rich fields (`code`, `message`, `severity`, `node_id`, `edge_id`, `path`, `expected`, `actual`, `suggestions`)
- `warnings[]`

Validation combines compiler checks and tenant-aware runtime references (for example model/tool existence).

SDK error surfaces for agent mutations now preserve structured backend validation details:
- `details` (raw structured payload when available)
- `validation_errors` (normalized list extracted from backend `detail.errors`)

## Legacy Removal Status
Removed from active path:
- staged subagent orchestration behavior for architect runtime
- `architect.run` runtime dispatch path
- `platform-agents` allowance for `architect.*` actions
- `backend/artifacts/builtin/platform_sdk/actions/architect.py`

## Primary Source Files
- `backend/app/services/registry_seeding.py`
- `backend/app/services/platform_architect_contracts.py`
- `backend/artifacts/builtin/platform_sdk/handler.py`
- `backend/artifacts/builtin/platform_sdk/actions/agents.py`
- `backend/artifacts/builtin/platform_sdk/actions/rag.py`
