Last Updated: 2026-04-12

## Scope
Historical agent-thread replay and per-turn trace hydration in the admin playground thread history flow.

## Test Files Present
- `frontend-reshet/src/__tests__/agent_thread_history/useAgentThreadHistory.test.tsx`

## Key Scenarios Covered
- Initial history fetch is scoped to the current user and the currently selected agent.
- Duplicate or corrupted `turn_index` values fall back to chronological ordering during thread replay.
- Assistant trace blocks are hydrated for every assistant turn, not only the latest turn.
- Thread replay now prefers persisted canonical `response_blocks` and only falls back to persisted `assistant_output_text` for older turns.
- Architect-worker style replay with a continued worker thread preserves the expected message order.
- Hydrated assistant response blocks do not duplicate the final assistant text for the continued worker turn.
- Assistant replay messages retain canonical per-run token usage for thread-page tooltips.
- Legacy turns without persisted blocks still render safely from `assistant_output_text` without rehydrating run traces.

## Last Run
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/agent_thread_history/useAgentThreadHistory.test.tsx src/__tests__/agent_playground/useAgentRunController.test.tsx src/__tests__/assistant_response_ui/normalizer.test.ts`
- Date: 2026-04-12 Asia/Hebron
- Result: Pass (`25 passed`)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/agent_thread_history/useAgentThreadHistory.test.tsx`
- Date: 2026-04-12 Asia/Hebron
- Result: Pass (`4 passed`)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/agent_thread_history/useAgentThreadHistory.test.tsx`
- Date: 2026-04-05 19:58 EEST
- Result: Pass (`3 passed`)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/admin_threads/admin_thread_page.test.tsx src/__tests__/agent_thread_history/useAgentThreadHistory.test.tsx`
- Date: 2026-03-27 Asia/Hebron
- Result: Pass (`2 passed`)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/assistant_response_ui/normalizer.test.ts src/__tests__/agent_thread_history/useAgentThreadHistory.test.tsx`
- Date: 2026-03-16 15:18 EET
- Result: Pass (`7 passed`)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/agent_thread_history/useAgentThreadHistory.test.tsx`
- Date: 2026-03-29 Asia/Hebron
- Result: Pass (`2 passed`)

## Known Gaps / Follow-ups
- Add a page-level playground regression once the admin thread history surface is refactored into smaller test seams.
