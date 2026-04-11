Last Updated: 2026-04-12

# MCP Servers MVP

## Scope
- Remote Streamable HTTP MCP servers only
- MCP lifecycle support for `initialize`, `notifications/initialized`, `tools/list`, and `tools/call`
- Tenant-owned MCP server records
- Per-user OAuth account linking for protected MCP servers
- Agent-level MCP server mounts with whole-server tool exposure

## Domain Objects
- `McpServer`: MCP server connection, auth mode, discovery/auth metadata, latest tool snapshot version
- `McpDiscoveredTool`: cached discovered tool metadata for a specific snapshot version
- `McpAgentMount`: attaches one MCP server to one agent and pins an applied snapshot version
- `McpUserAccountConnection`: encrypted per-user token set for one MCP server
- `McpOauthState`: transient PKCE state for the OAuth authorization-code callback

## Auth Modes
- `none`
- `static_bearer`
- `static_headers`
- `oauth_user_account`

## OAuth Behavior
- Missing auth is detected from `401` plus `WWW-Authenticate`
- Protected Resource Metadata and authorization-server metadata are discovered from the MCP server
- PKCE is always used
- Client selection order:
  1. admin-configured client id/secret on the server record
  2. stored dynamic-registration result
  3. client metadata document mode when supported
  4. dynamic client registration when supported
  5. fail and require admin-configured client credentials
- Tokens are encrypted at rest and refreshed automatically before use when possible

## Agent Runtime Behavior
- Agents mount MCP servers, not individual MCP tools
- Mounted tools are projected into runtime as virtual tools, separate from `ToolRegistry`
- Existing mounts stay pinned to `applied_snapshot_version`
- New discoveries are not exposed to mounted agents until the mount explicitly applies the latest snapshot
- Runtime auth source:
  - static auth uses the MCP server’s shared credential
  - OAuth auth uses the initiating user’s linked account

## Runtime Interruptions
- Missing or stale OAuth account link emits `mcp.auth_required`
- `ask` mount policy emits `approval.request`
- The current MVP surfaces these as runtime events in chat/UI; it does not yet pause-and-resume the agent run automatically

## Public API Surface
- `/mcp/servers`
- `/mcp/servers/{id}`
- `/mcp/servers/{id}/test`
- `/mcp/servers/{id}/sync`
- `/mcp/servers/{id}/tools`
- `/mcp/servers/{id}/auth/start`
- `/mcp/auth/callback`
- `/mcp/servers/{id}/account/me`
- `/agents/{id}/mcp-mounts`

## Admin UX
- Settings page: create, test, sync, and connect MCP servers
- Agent builder: attach or detach MCP servers and apply the latest discovered snapshot
