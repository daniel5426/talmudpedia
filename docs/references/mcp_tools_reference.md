# MCP Tools Reference

Last Updated: 2026-03-18

This document is the canonical reference for current MCP tool behavior.

## Purpose

MCP is one implementation type inside the broader tools domain. This document focuses on MCP-specific runtime behavior and governance concerns.

## Current Registration Model

MCP tools are represented as standard tool records using:
- `implementation_type = mcp`
- or `config_schema.implementation.type = "mcp"` as fallback interpretation

The built-in catalog also includes `mcp_call` as a built-in runtime entry.

## Current Required Config

Current effective config fields:
- `implementation.server_url`
- `implementation.tool_name`
- `implementation.headers` (optional)
- `execution.timeout_s` (optional)

## Current Request Contract

Runtime sends JSON-RPC over HTTP with:
- method: `tools/call`
- params:
  - `name`
  - `arguments`

If node input includes an `arguments` object, that is used. Otherwise the full input payload is passed as `arguments`.

## Current Response Handling

- error response => execution failure
- missing `result` => execution failure
- non-object `result` => wrapped into `{ "result": ... }`

## Current Shared Guardrails

MCP tools still inherit normal tool guardrails:
- tenant/global visibility checks
- active-state requirement
- published requirement in production mode

Current MCP transport policy:
- `server_url` must use `http` or `https`
- URL-embedded credentials are rejected
- private and loopback hosts are blocked by default
- `MCP_ALLOW_PRIVATE_HOSTS=true` can explicitly allow private hosts for local/dev setups
- `MCP_ALLOWED_HOSTS` can restrict outbound MCP calls to a hostname allowlist
- malformed headers, invalid JSON responses, and transport failures are normalized into stable runtime errors

## Current Governance Gaps

Current gaps still worth treating as open:
- no explicit MCP host allowlist at runtime
- headers may still be stored in tool config even though reads redact sensitive values
- no MCP-specific retry/circuit-breaker policy beyond generic tool execution behavior

## Canonical Implementation References

- `backend/app/api/routers/tools.py`
- `backend/app/agent/executors/tool.py`
