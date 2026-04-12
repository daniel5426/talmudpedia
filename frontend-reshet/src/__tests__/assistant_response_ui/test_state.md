Last Updated: 2026-04-12

## Scope
Shared assistant-response normalization and timeline rendering used by the agent builder execute panel and the agent playground.

## Test Files Present
- `frontend-reshet/src/__tests__/assistant_response_ui/normalizer.test.ts`
- `frontend-reshet/src/__tests__/assistant_response_ui/renderer.test.tsx`
- `frontend-reshet/src/__tests__/assistant_response_ui/trace_loader.test.ts`
- `frontend-reshet/src/__tests__/assistant_response_ui/chat_context_status.test.tsx`

## Key Scenarios Covered
- Tool lifecycle events stay inline in chronological order with assistant text.
- Synthesized tool reasoning events do not create duplicate visual rows.
- Persisted execution-trace tool lifecycle events normalize back into tool-call blocks.
- Structured architect JSON responses are converted into user-facing text.
- The shared renderer handles tool rows, plain text, and inline approval blocks in one flow.
- Shared tool-call titles collapse verbose platform SDK summaries into shorter action labels.
- Active tool and thinking labels shimmer while streaming.
- Historical assistant messages do not inherit active loading shimmer from newer runs.
- Tool rows can expand to reveal the stored summary text when the summary differs from the short title.
- Tool rows can show an inline thread redirect affordance when a tool call resolves to a child thread id.
- Persisted run events can be replayed back into assistant response blocks for lazy trace loading and latest-turn thread hydration.
- Finalization collapses duplicate assistant text blocks when persisted replay and saved final text resolve to the same assistant message.
- Shared chat context widget renders canonical context-window input usage instead of legacy estimated-total-with-reserve semantics.
- Timeline assistant text blocks now stay on the same plain-text renderer during and after live streaming, avoiding a completion-time renderer swap.
- Shared stream normalization preserves `assistant_text -> tool -> assistant_text` chronology instead of collapsing all live text into one block.
- Shared stream normalization drops provider-native tool delta objects like MCP `tool_use` / `input_json_delta` chunks so raw structured payloads do not leak into live assistant text.

## Last Run
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/assistant_response_ui/normalizer.test.ts src/__tests__/agent_playground/useAgentRunController.test.tsx --watch=false`
- Date: 2026-04-12 15:44:55 EEST
- Result: PASS (`2 suites, 18 tests`)

- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/assistant_response_ui/renderer.test.tsx src/__tests__/agent_playground/useAgentRunController.test.tsx --watch=false`
- Date: 2026-04-09 Asia/Hebron
- Result: PASS (`2 suites, 15 tests`)
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/assistant_response_ui/normalizer.test.ts src/__tests__/assistant_response_ui/trace_loader.test.ts src/__tests__/assistant_response_ui/renderer.test.tsx --watch=false`
- Date: 2026-04-09 Asia/Hebron
- Result: PASS (`3 suites, 12 tests`)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/assistant_response_ui/renderer.test.tsx`
- Date: 2026-04-06 Asia/Hebron
- Result: PASS (`3 passed`)
- Command: `pnpm --dir talmudpedia-standalone typecheck`
- Date: 2026-04-05 Asia/Hebron
- Result: PASS
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/assistant_response_ui/chat_context_status.test.tsx`
- Date: 2026-03-29 Asia/Hebron
- Result: PASS (`1 passed`)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/assistant_response_ui/normalizer.test.ts src/__tests__/assistant_response_ui/renderer.test.tsx`
- Date: 2026-03-10 19:02:00 EET
- Result: Pass
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/assistant_response_ui/normalizer.test.ts src/__tests__/assistant_response_ui/renderer.test.tsx src/__tests__/assistant_response_ui/trace_loader.test.ts`
- Date: 2026-03-12 05:49 EET
- Result: Partial fail (`trace_loader.test.ts` passed; existing unrelated renderer shimmer assertions failed`)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/assistant_response_ui/trace_loader.test.ts src/__tests__/assistant_response_ui/normalizer.test.ts`
- Date: 2026-03-12 05:51 EET
- Result: Pass
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/assistant_response_ui/normalizer.test.ts src/__tests__/agent_thread_history/useAgentThreadHistory.test.tsx`
- Date: 2026-03-16 15:18 EET
- Result: Pass (`7 passed`)

## Known Gaps / Follow-ups
- Add end-to-end controller tests once the playground stream handling is covered directly.
- Add a dedicated thread-history rehydration test for `/admin/threads/{thread_id}` + `/agents/runs/{run_id}/events`.
- Add historical-thread best-effort replay coverage if old-thread rendering becomes a product requirement.
