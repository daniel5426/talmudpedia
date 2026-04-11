Last Updated: 2026-04-12

# MCP Support Test State

## Scope
- MCP server domain objects
- Agent MCP mounts
- OAuth start-state creation
- Runtime virtual-tool resolution and gating

## Test Files Present
- `test_mcp_support.py`

## Key Scenarios Covered
- Mounted MCP snapshots project into runtime virtual tools
- OAuth-backed mounts fail clearly when no linked user account is available
- `ask` approval policy blocks runtime execution before transport
- OAuth start builds a PKCE state row and uses client metadata document mode
- API create-server and attach-mount flows work end-to-end

## Last Run
- Command: `cd backend && pytest -q tests/mcp_support/test_mcp_support.py`
- Date/Time: 2026-04-12
- Result: Pass (5 passed)

## Known Gaps
- No live external MCP transport integration test yet
- No token refresh callback-path test yet
- No frontend UI test coverage yet
