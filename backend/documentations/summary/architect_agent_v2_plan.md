# Architect Agent v2 — Full‑Control, Multi‑Agent Builder (API‑Only, Draft‑Only)

Last Updated: 2026-02-06

## Summary
Design and implement a multi‑agent “Architect” system that can introspect platform capabilities, create draft agents/workflows/tools/artifacts, and run multi‑case tests before returning a final report. The system is API‑only and uses service tokens for privileged internal calls. It upgrades the current linear Platform Architect into a multi‑agent orchestrator while keeping all mutations in draft status.

## Goals
- Full platform control for building agents/workflows through APIs only.
- Multi‑agent workload with explicit roles and structured outputs.
- Ability to create custom artifacts, tools, and agent graphs.
- Multi‑case test execution for newly created agents.
- Draft‑only creation (no auto‑publish).

## Non‑Goals
- Automated production publishing.
- Filesystem access by the agent directly.
- Hard limits or budgets (deferred).

## Architecture

### 1) Multi‑Agent Roles (All are platform Agents)
1. Architect Orchestrator  
Owns the user request, coordinates sub‑agents, validates plans, executes build steps, runs tests, and returns a final report.

2. Catalog/Introspector Agent  
Uses SDK tool to fetch current catalog of tools, nodes, artifacts, models.

3. Planner Agent  
Produces a strict Plan JSON with actions and test cases.

4. Builder Agent  
Converts plan actions into GraphSpec v1 (agents) or DAG JSON (pipelines).

5. Coder Agent  
Generates artifacts and tools for missing capabilities.

6. Tester Agent  
Runs multi‑case tests and produces a structured test report.

### 2) Execution Model
- The Orchestrator uses a single SDK Tool to call all platform APIs.
- Sub‑agents are invoked via a new SDK tool action `run_agent`.
- All creation actions are draft‑only.

### 3) Draft‑Only Enforcement
- Agents: created via `/agents` with default draft status.
- Tools: created via `/tools` with `status = DRAFT`.
- Artifacts: created as draft via `/admin/artifacts`, promoted only if explicitly requested.

## Data Contracts

### A) Plan JSON (Planner Output)
```json
{
  "intent": "string",
  "actions": [
    {
      "id": "string",
      "type": "create_artifact_draft | promote_artifact | create_tool | deploy_agent | deploy_rag_pipeline | run_tests",
      "payload": {},
      "depends_on": ["action_id"]
    }
  ],
  "tests": [
    {
      "name": "string",
      "agent_target": {"agent_id": "uuid" | "agent_slug": "string"},
      "input": {"text": "string", "context": {}},
      "assertions": [
        {"type": "contains | exact | jsonpath", "path": "output.text", "expected": "string"}
      ]
    }
  ]
}
```

### B) Test Report Schema (Tester Output)
```json
{
  "tests": [
    {"name": "string", "status": "passed|failed", "details": "...", "run_id": "uuid"}
  ],
  "summary": {"passed": 0, "failed": 0}
}
```

## SDK Tool Extensions (Platform SDK Tool)
Add new actions to `backend/artifacts/builtin/platform_sdk/handler.py`:

1. `create_artifact_draft`  
Uses `/admin/artifacts` to create draft artifacts with `scope` = `rag|agent|both`.

2. `promote_artifact`  
Uses `/admin/artifacts/{id}/promote` to create file‑based artifacts (still draft tools by default).

3. `create_tool`  
Uses `/tools` to create tool entries (default `status: DRAFT`). Supports `implementation_type` = `artifact|http|mcp|function`.

4. `run_agent`  
Calls `/agents/{id}/execute` for test runs (non‑streaming).  
Optional future: `/agents/{id}/stream?mode=debug` for rich traces.

5. `run_tests`  
Executes multi‑case tests by calling `run_agent` and evaluating assertions.

## Auth/RBAC Adjustments (Service Tokens)
To keep API‑only and internal execution safe:
- Update `/tools` and `/admin/artifacts` to accept service tokens by using `get_current_user_or_service`.
- Ensure tenant context is enforced for service tokens (same pattern as `/agents` and `/admin/pipelines`).

## Orchestrator Flow (High‑Level)
1. Fetch Catalog via SDK.
2. Run Planner Agent → Plan JSON.
3. Validate Plan via SDK `validate_plan`.
4. Run Builder/Coder Agents to produce drafts and artifacts.
5. Execute Plan via SDK `execute_plan`.
6. Run Multi‑Case Tests via SDK `run_tests`.
7. Return Final Report with draft IDs + test results.

## Test Strategy
- Unit tests: SDK tool new actions, plan validator, test evaluator.
- Integration tests:
  - create artifact draft → promote → create tool  
  - deploy agent → run tests (multi‑case)
- Acceptance:
  - Orchestrator returns a full report with draft assets and test status.
  - No assets are published automatically.

## Public API / Interface Changes
- `/admin/artifacts` and `/tools` accept service tokens (internal only).
- SDK Tool exposes new actions for artifacts/tools/tests.

## Rollout Plan
1. Extend SDK tool actions + auth dependencies.
2. Seed sub‑agents (Catalog, Planner, Builder, Coder, Tester).
3. Upgrade Orchestrator agent graph to multi‑agent workflow.
4. Deprecate legacy linear Platform Architect or keep as fallback.

## Docs Updates (Required)
- `backend/documentations/platform_current_state.md`  
Update MCP/function tool capability and Architect flow.
- `backend/documentations/platform_agent_strategy.md`  
Replace linear MVP with multi‑agent architecture.
- `backend/documentations/architect_agent_debug_report.md`  
Update to reflect multi‑agent, draft‑only, test‑first execution.

## Assumptions
- Draft creation is acceptable for all assets.
- Agent execution works on draft agents via `/agents/{id}/execute`.
- Service tokens can be used for internal administrative calls once auth dependencies are updated.
- Assertion‑based evaluation is sufficient for multi‑case tests.
