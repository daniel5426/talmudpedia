# Platform Architect Agent Redesign — Architecture & Implementation Guide

## Summary
The Platform Architect is being refactored into a SaaS-ready meta-agent that can build and deploy agents and RAG pipelines reliably. The new design introduces a **service-token auth pattern**, **simplified token resolution**, and **server-side plan validation**. We keep the **linear flow** for now, but make it safer and more debuggable.

---

## Current Issues (Pre-Redesign)
- **401 on catalog fetch**: `/admin/pipelines/catalog` requires admin auth; SDK calls lacked privileged claims.
- **Linear flow only**: No routing or approval steps; failures were silent.
- **Mocked tests**: Unit tests bypassed real HTTP calls, masking auth bugs.
- **Token resolution chaos**: Multiple env vars and inconsistent fallback behavior.
- **Corrupted tests**: `test_architect_capabilities.py` was invalid.

---

## Redesign Overview

### 1) Service Token Pattern (Auth Fix)
Internal SDK calls require admin-like access without exposing user tokens. The new pattern:
- Mint **short-lived** (5 min) service tokens with claim `role="platform-service"`.
- Tokens are signed using `PLATFORM_SERVICE_SECRET`.
- Admin endpoints accept service tokens for internal calls.

### 2) Simplified Token Resolution
The SDK tool now resolves auth in a strict order:
1. Service token (minted from `PLATFORM_SERVICE_SECRET`, requires tenant)
2. Explicit token from context/inputs
3. Environment client token (`PLATFORM_API_KEY` / `API_KEY`)

### 3) Validation Before Execution
The tool now validates plans before executing:
- `validate_plan` is a first-class action.
- `execute_plan` always runs validation and skips execution if invalid.

### 4) Linear Flow (Deliberate Choice)
Conditional routing is not added yet. The flow remains:
`Start → Catalog Tool → Planner → Execute Tool → End`

Validation adds safety without requiring engine-level branching.

---

## Files & Responsibilities

### New
- `backend/app/core/internal_token.py`
  - `create_service_token(tenant_id, subject="platform-service")`
  - `decode_service_token(token)`

### Modified
- `backend/app/core/security.py`
  - Re-exports service token helpers
- `backend/app/api/dependencies.py`
  - `get_current_service_caller`
  - `get_current_user_or_service`
- `backend/app/api/routers/rag_pipelines.py`
  - `/catalog` accepts service tokens
  - `/visual-pipelines` supports service callers
- `backend/app/api/routers/agents.py`
  - `/agents` accepts service tokens
- `backend/artifacts/builtin/platform_sdk/handler.py`
  - Adds `validate_plan`
  - Simplifies `_resolve_auth`
  - Validates before execution
- `backend/app/services/registry_seeding.py`
  - Prompt updates and tool schema updates
- `backend/tests/test_architect_capabilities.py`
  - Rebuilt clean tests
- `backend/tests/test_platform_architect_integration.py`
  - Real integration tests for service tokens

---

## Service Token Design

**Claims**
- `role = "platform-service"`
- `tenant_id = <uuid>`
- `exp = now + 5 minutes`

**Authorization**
- Used for internal SDK calls
- Accepted on `/admin/pipelines/*` and `/agents`

---

## Plan Validation Behavior

### Supported Actions
- `fetch_catalog`
- `validate_plan`
- `execute_plan`
- `respond`

### Validation Rules
- `create_custom_node`: require `name` + `python_code`
- `deploy_rag_pipeline`: validate DAG and operators using `PipelineCompiler`
- `deploy_agent`: validate structure using `AgentCompiler`
- Validate operator/node types against catalog when available

### Execution Behavior
- `execute_plan` always validates first
- Validation errors return `status="validation_failed"`

---

## Environment Variables

### Required
- `PLATFORM_SERVICE_SECRET` (new, required for internal service tokens)

### Deprecated
- `PLATFORM_ADMIN_API_KEY`
- `ADMIN_API_KEY`

### Still Supported (Client-side)
- `PLATFORM_API_KEY`
- `API_KEY`

---

## Test Plan

### Unit
- `test_platform_sdk_tool.py`
  - validate_plan + skip-on-fail logic
- `test_architect_capabilities.py`
  - validation error handling
  - execution skip
  - success path

### Integration
- `test_platform_architect_integration.py`
  - service token encode/decode
  - catalog fetch with service token
  - agent create with service token

---

## Manual Verification
1. Start backend
2. Generate service token
3. Call `/admin/pipelines/catalog` with service token
4. Run Architect agent in UI
5. Verify new agent appears in Agents list

---

## Decision Log
- **Routing**: keep linear flow for now
- **Auth**: use service tokens for internal calls
- **Env**: consolidate into `PLATFORM_SERVICE_SECRET`
