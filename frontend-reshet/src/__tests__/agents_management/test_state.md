# Agents Management Test State

Last Updated: 2026-03-18

## Scope
Frontend Agents page management actions, including delete flow wiring and export-to-tool dialog behavior.

## Test files present
- `agents_page_delete_action.test.tsx`
- `agents_page_export_tool.test.tsx`

## Key scenarios covered
- Clicking the per-agent overflow menu delete action triggers `agentService.deleteAgent` with the agent id.
- Clicking the per-agent overflow menu copy action writes the agent id to the clipboard.
- Export-mode routing opens the agent export dialog and submits `agentService.exportAgentTool` with the selected agent/tool metadata.

## Last run command + date/time + result
- Command: `npm test -- --runInBand src/__tests__/agents_management/agents_page_delete_action.test.tsx src/__tests__/agents_management/agents_page_export_tool.test.tsx`
- Date/Time: 2026-03-18 19:12 Asia/Hebron
- Result: pass (`2 suites, 3 tests`)

## Known gaps or follow-ups
- Add a test for cancel path (`window.confirm` returns false).
- Add integration test to verify list refresh/error banner behavior after failed deletion.
