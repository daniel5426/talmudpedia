# MCP Tools Overview

Last Updated: 2026-02-06

## Purpose
MCP tools let agents invoke external capabilities via the MCP protocol, using a simple HTTP JSON-RPC bridge. This enables pluggable, vendor-agnostic tools without baking logic into the agent runtime.

## Execution Model
- MCP tools are regular Tools with `implementation_type: mcp`.
- The Tool executor sends a JSON-RPC request using method `tools/call`.
- Results are returned as tool outputs and surfaced to the agent state/context.

## Required Configuration
`implementation_config` fields:
- `type`: `"mcp"`
- `server_url`: HTTP endpoint that accepts JSON-RPC
- `tool_name`: MCP tool name
- `headers` (optional): forwarded as HTTP headers for auth

Example:
```json
{
  "implementation": {
    "type": "mcp",
    "server_url": "https://mcp.example.com/tools",
    "tool_name": "search",
    "headers": {"Authorization": "Bearer ..."}
  },
  "execution": {
    "timeout_s": 10
  }
}
```

## JSON-RPC Shape
```json
{
  "jsonrpc": "2.0",
  "id": "<uuid>",
  "method": "tools/call",
  "params": {
    "name": "<tool_name>",
    "arguments": {"...": "..."}
  }
}
```

## Error Handling
- If the MCP server returns an `error`, the tool run fails with a clear message.
- If `result` is missing, the tool run fails with a validation error.

## Security Notes
- Use `headers` to pass auth tokens or signatures.
- The tool executor does not store or log headers.

## Validation Status
Validated locally with a JSON-RPC stub server (HTTP 200 + `result`).
