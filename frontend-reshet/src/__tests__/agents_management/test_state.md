# Agents Management Test State

Last Updated: 2026-03-24

## Scope
Frontend Agents page management actions, including delete flow wiring and export-to-tool dialog behavior.

## Test files present
- `agents_page_delete_action.test.tsx`
- `agents_page_export_tool.test.tsx`

## Key scenarios covered
- Clicking the per-agent overflow menu delete action triggers `agentService.deleteAgent` with the agent id.
- Clicking the per-agent overflow menu copy action writes the agent id to the clipboard.
- Export-mode routing opens the agent export dialog and submits `agentService.exportAgentTool` with the selected agent/tool metadata.
- The export dialog exposes a single artifact-style split tree + details schema editor.
- The export dialog lets the user edit the selected schema field from the builder before submission.
- The export dialog lets the user switch to raw JSON editing and export from that mode.

## Last run command + date/time + result
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/agents_management/agents_page_export_tool.test.tsx`
- Date/Time: 2026-03-24 19:44 EET
- Result: pass (`1 suite, 3 tests`)

## Known gaps or follow-ups
- Add a test for cancel path (`window.confirm` returns false).
- Add integration test to verify list refresh/error banner behavior after failed deletion.
- Browser-level coverage still does not verify real CodeMirror scrolling behavior in the JSON tab.
