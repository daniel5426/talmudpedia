# Agents Management Test State

Last Updated: 2026-04-21

## Scope
Frontend Agents page management actions, including delete flow wiring and the card-level make-tool bind flow.

## Test files present
- `agents_page_delete_action.test.tsx`
- `agents_page_tool_binding.test.tsx`

## Key scenarios covered
- Clicking the per-agent overflow menu delete action triggers `agentService.deleteAgent` with the agent id.
- Clicking the per-agent overflow menu copy action writes the agent id to the clipboard.
- Clicking `Make tool` from the per-agent overflow menu triggers the instant bind/sync action with no export dialog.
- Agent cards show bound tool status directly in the footer when the backend reports an active agent-bound tool.
- Agent page mocks now follow the canonical list envelope used by `agentService.listAgents` (`items`, `total`, `has_more`, `skip`, `limit`, `view`).
- The agents page project-switch remount path preserves the same actions while reloading the page against the newly active project dataset.

## Last run command + date/time + result
- Command: `cd frontend-reshet && npm test -- --runTestsByPath src/__tests__/agents_management/agents_page_delete_action.test.tsx src/__tests__/agents_management/agents_page_tool_binding.test.tsx --watch=false`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: pass (`2 suites, 4 tests`)
- Command: `pnpm exec jest src/__tests__/agents_management/agents_page_delete_action.test.tsx src/__tests__/agents_management/agents_page_tool_binding.test.tsx --runInBand`
- Date/Time: 2026-04-14 23:18 EEST
- Result: pass (`2 suites, 4 tests`)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/agents_management/agents_page_tool_binding.test.tsx --watch=false`
- Date/Time: 2026-03-31 Asia/Hebron
- Result: pass (`1 suite, 2 tests`)
- Command: `cd frontend-reshet && npm exec pnpm -- test -- --runTestsByPath src/__tests__/agents_management/agents_page_tool_binding.test.tsx`
- Date/Time: 2026-04-21 Asia/Hebron
- Result: pass (`1 suite`)

## Known gaps or follow-ups
- Add a test for cancel path (`window.confirm` returns false).
- Add integration test to verify list refresh/error banner behavior after failed deletion.
