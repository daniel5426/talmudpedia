# Legacy Plan And Summary Map

Last Updated: 2026-03-10

This document maps the remaining legacy planning/history folders into the new documentation system.

## Current Legacy Folders

- `backend/documentations/Plans/`
- `backend/documentations/summary/`

## Current Interpretation Rules

### `backend/documentations/Plans/`

Treat these as legacy execution-plan documents.

Until individually reviewed:
- if the work is still active, it belongs conceptually in `docs/exec-plans/active/`
- if the work is finished or historical, it belongs conceptually in `docs/exec-plans/completed/`

Current files in that folder:
- `Agents_Tools_Production_Readiness_Refinement_Testing_Plan.md`
- `AppsBuilder_Current_Implementation_Overview.md`
- `Base44_ConfigMigration_Plan.md`
- `CodingAgent_PerRunSandboxIsolation_Implementation.md`

### `backend/documentations/summary/`

This folder is mixed and should not be treated as one document type.

Until individually reviewed:
- implementation handoffs and completion notes map conceptually to `docs/exec-plans/completed/`
- architecture-gap notes can be promoted into `docs/design-docs/` if still canonical
- generated protocol dumps belong in `docs/generated/`
- narrow technical references can remain historical notes until promoted or archived

## Known Generated Items

The following files are clearly generated artifacts:
- `opencode_tools_protocol_probe_2026-02-25.json`
- `opencode_tools_protocol_probe_legacy_2026-02-25.json`

These map conceptually to `docs/generated/`.

## Migration Rule

Do not bulk-move every file immediately.

Instead:
1. classify by intent
2. promote canonical truth into `docs/`
3. leave old files as historical context unless they are actively harmful or contradictory
