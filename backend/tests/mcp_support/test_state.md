Last Updated: 2026-04-21

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
- Membership fixtures no longer depend on the removed legacy org-membership role enum

## Last Run
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/mcp_support`
- Date/Time: 2026-04-21 21:13 EEST
- Result: FAIL (`1 failed, 4 passed`). `test_mcp_runtime_lists_virtual_tools_for_applied_snapshot` still expects the old virtual-tool slug format.
- Command: `cd backend && pytest -q tests/mcp_support/test_mcp_support.py`
- Date/Time: 2026-04-12
- Result: Pass (5 passed)

## Known Gaps
- No live external MCP transport integration test yet
- No token refresh callback-path test yet
- No frontend UI test coverage yet
