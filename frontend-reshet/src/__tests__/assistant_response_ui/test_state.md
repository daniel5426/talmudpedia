Last Updated: 2026-03-10

## Scope
Shared assistant-response normalization and timeline rendering used by the agent builder execute panel and the agent playground.

## Test Files Present
- `frontend-reshet/src/__tests__/assistant_response_ui/normalizer.test.ts`
- `frontend-reshet/src/__tests__/assistant_response_ui/renderer.test.tsx`

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

## Last Run
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/assistant_response_ui/normalizer.test.ts src/__tests__/assistant_response_ui/renderer.test.tsx`
- Date: 2026-03-10 19:02:00 EET
- Result: Pass

## Known Gaps / Follow-ups
- Add end-to-end controller tests once the playground stream handling is covered directly.
- Add a dedicated thread-history rehydration test for `/admin/threads/{thread_id}` + `/agents/runs/{run_id}/events`.
- Add historical-thread best-effort replay coverage if old-thread rendering becomes a product requirement.
