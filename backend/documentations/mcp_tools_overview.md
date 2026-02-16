# MCP Tools Overview

Last Updated: 2026-02-16

## Purpose
This document captures:
- MCP tools runtime behavior as currently implemented.
- How MCP fits into the broader platform status.
- Tenant / org / unit implications and a concrete rethink direction.

## Platform Snapshot (Current)
Based on the current documentation set (`platform_current_state.md`, `tools_overview.md`) and backend code:
- Agent and RAG domains are both service-layer based and tenant-scoped.
- Tools are a first-class domain with typed implementations (`http`, `function`, `mcp`, `rag_retrieval`, `agent_call`, `artifact`).
- Runtime guardrails are active: production requires `published` tools; inactive tools are blocked.
- Auth is hybrid user/workload token based, but tenant-context resolution is not fully standardized across routers yet.

## MCP Runtime: What Exists Today

### Registration / Type
- MCP is represented as standard Tool records with:
  - `implementation_type = MCP`, or
  - `config_schema.implementation.type = "mcp"` (fallback path).
- Built-in catalog includes `mcp_call` as a global built-in entry.

### Required Config (effective)
From runtime behavior (`ToolNodeExecutor` + `call_mcp_tool`):
- `implementation.server_url` (required)
- `implementation.tool_name` (required)
- `implementation.headers` (optional passthrough)
- `execution.timeout_s` (optional)

Example:
```json
{
  "implementation": {
    "type": "mcp",
    "server_url": "https://mcp.example.com/tools",
    "tool_name": "search",
    "headers": {
      "Authorization": "Bearer <token>"
    }
  },
  "execution": {
    "timeout_s": 10
  }
}
```

### Request Contract
Runtime sends HTTP POST JSON-RPC:
```json
{
  "jsonrpc": "2.0",
  "id": "<uuid>",
  "method": "tools/call",
  "params": {
    "name": "<tool_name>",
    "arguments": { "...": "..." }
  }
}
```

Input mapping:
- If node input includes `arguments` object, that is used.
- Otherwise whole input payload is passed as `arguments`.

### Response Contract
- If response has `error`, execution fails.
- If response is missing `result`, execution fails.
- If `result` is non-object, runtime wraps it as `{ "result": <value> }`.

### Runtime Guardrails that Also Apply to MCP
- Tool row must be tenant-visible (`tenant_id == current tenant` or global).
- Tool must be active.
- In production mode, tool must be published.

## MCP Security / Governance Notes (Current State)

### Strengths
- Sensitive fields are redacted in Tools API responses.
- Tenant visibility rules are enforced on tool lookup.
- Workload-token flow exists for secure internal calls in adjacent domains.

### Gaps
- No explicit MCP host allowlist / egress policy in tool runtime.
- `headers` can still be persisted in tool config (redacted on read, but stored).
- No MCP-specific approval gate beyond standard tool publish/execute controls.
- No circuit-breaker or retry/backoff policy specific to MCP transport failures.

## Tenant / Org / Unit Status (Current State)

### Current Model
- `Tenant`: hard isolation boundary used widely across core runtime tables.
- `OrgMembership`: links user to tenant and role.
- `OrgUnit`: hierarchical structure exists and is still exposed by `/api/tenants/{tenant_slug}/org-units`.

### Practical Adoption Pattern
- Tenant scoping is pervasive and enforced across critical runtime paths.
- `org_unit_id` is sparse in core models (primarily `visual_pipelines`, `audit_logs`, and `org_memberships`).
- Many runtime services and routers do not enforce org-unit boundaries for data access.

### Key Inconsistency
Tenant context resolution is mixed:
- Some routes honor explicit tenant selection (for example via `X-Tenant-ID`).
- Some routes fall back to "first membership" or "first tenant" behavior.

This can create ambiguous behavior for users in multiple tenants and makes policy guarantees harder to reason about.

## Rethink Proposal (Tenant / Org / Unit)

### Recommended Direction
- Keep **Tenant** as the only hard data-isolation boundary.
- Treat **OrgRole** as tenant-level authorization baseline.
- Make **OrgUnit** explicitly optional and policy-scoped (not implied by default context resolution).

### Concrete Target State
1. Introduce one canonical `PrincipalContext` resolver used by all secure routers.
2. Require explicit tenant context for secure endpoints (token claim and/or `X-Tenant-ID`), remove fallback-to-first-tenant behavior.
3. Keep `org_unit_id` as optional metadata/policy scope for selected domains (pipelines/audit/workflows), not as global enforcement everywhere.
4. Add feature-flagged org-unit policy checks only where business need is clear.

### Suggested Rollout
1. Observability phase:
   - Log and measure every fallback tenant-context resolution path.
2. Standardization phase:
   - Migrate routers to shared principal resolver and explicit tenant selection.
3. Enforcement phase:
   - Remove fallback behavior and fail fast on missing/ambiguous tenant context.
4. Org-unit hardening phase (optional):
   - Add unit-aware policy checks only in domains that need delegated sub-tenant governance.

## MCP-Specific Implication of the Rethink
For MCP tools specifically, standardizing tenant context removes ambiguity in which tenant’s tool config and credentials are used, and makes host-level governance (allowlist / policy) implementable in a single place.
