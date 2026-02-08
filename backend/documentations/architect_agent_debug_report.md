# Platform Architect Agent v2 — Architecture & Implementation Guide

Last Updated: 2026-02-07

## Summary
The Platform Architect is evolving from a linear, single‑agent flow into a **multi‑agent, draft‑only, test‑first** system. This v2 design uses delegated workload-token auth with strict scope checks and plan validation, while introducing orchestrated sub‑agents and multi‑case testing.

---

## Key Changes from v1
- **Multi‑Agent Orchestration**: Planner, Builder, Coder, Tester are separate agents.
- **Draft‑Only Creation**: No auto‑publish for agents, tools, or artifacts.
- **Multi‑Case Tests**: Every created agent is validated across multiple inputs.
- **Expanded SDK Tool**: New actions for artifact/tool creation and test execution.

---

## Core Flow (v2)
1. **Fetch Catalog** via SDK tool.
2. **Planner Agent** produces strict Plan JSON.
3. **Validate Plan** server‑side.
4. **Builder/Coder Agents** create draft artifacts/tools/agents.
5. **Tester Agent** runs multi‑case test suite.
6. **Orchestrator** returns final report with draft IDs + test results.

---

## Runtime Auth Design (current)
**Token Type**
- Delegated workload token (`token_use = workload_delegated`)
- Short-lived (default ~5 minutes)

**Authorization**
- Used for internal SDK calls made by artifacts/tools/agent runtime
- Scope-checked on secure endpoints via `require_scopes(...)`
- Legacy service/API-key fallback is removed on migrated secure paths

**Reference Docs**
- `backend/documentations/authentication_overview.md`
- `backend/documentations/service_token_auth.md`
- `backend/documentations/workload_delegation_auth_design.md`

---

## SDK Tool Actions (v2 implemented)
- `fetch_catalog`
- `validate_plan`
- `execute_plan`
- `create_artifact_draft`
- `promote_artifact`
- `create_tool`
- `run_agent`
- `run_tests`

---

## Draft‑Only Policy
- All created assets are drafts by default.
- Publishing requires explicit human approval.

---

## Testing Model
- **Multi‑case** scenarios (normal, boundary, failure).
- Tests run via `run_agent` action.
- Results summarized in a structured report.

---

## Open Items
- Harden prompts and output schemas for sub‑agents to reduce variance.
- Add telemetry for draft asset creation and test runs.
- Expand `run_tests` assertion types (numeric thresholds, schema checks).
