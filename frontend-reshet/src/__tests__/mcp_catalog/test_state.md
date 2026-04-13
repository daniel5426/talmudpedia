Last Updated: 2026-04-13

# MCP Catalog Test State

## Scope
- Frontend canonicalization of MCP catalog providers when duplicate server rows exist.

## Test Files Present
- `integration_catalog.test.ts`

## Key Scenarios Covered
- Legacy provider URLs still map to the correct catalog slug.
- Canonical catalog endpoints win over legacy duplicates.
- Active connection state wins when duplicate rows share the same provider mapping.

## Last Run
- Command: `pnpm test -- --runInBand src/__tests__/mcp_catalog/integration_catalog.test.ts`
- Date: 2026-04-13
- Result: Pass

## Known Gaps
- No browser-level test yet for the MCP settings page or agent builder dialog.
