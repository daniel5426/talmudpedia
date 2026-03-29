# Artifact Coding Agent Frontend Tests

Last Updated: 2026-03-29

## Scope

Track frontend coverage for the artifact page coding chat panel and artifact-specific copied chat stack.

## Test Files Present

- `chat_model.test.ts`
- `useArtifactCodingChat.test.tsx`

## Key Scenarios Intended

- right-side panel open/close behavior on the artifact page
- prompt submission sends current unsaved form state
- streamed draft snapshot updates mutate local artifact editor state
- create-mode `draft_key` continuity before first save
- saved-artifact prompts omit `draft_key` while create-mode prompts keep it
- history/session loading for saved artifacts and create drafts
- stop flow and pending-question flow
- manual abort now forwards streamed assistant text to the cancel API so a stopped run can persist the partial reply
- terminal run completion/failure settles lingering running tool rows
- history rebuild preserves assistant text segments around tool calls
- history rebuild can now recover partial assistant/tool history from run events even when no assistant message was durably persisted for that run
- live assistant segments can be finalized independently between tool calls

## Last Run

- Command: `pnpm test -- --runInBand src/__tests__/artifact_coding_agent/chat_model.test.ts`
- Date: 2026-03-25
- Result: pass
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifact_coding_agent/chat_model.test.ts`
- Date: 2026-03-25 Asia/Hebron
- Result: pass (`4 passed`)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifact_coding_agent/chat_model.test.ts src/__tests__/artifact_coding_agent/useArtifactCodingChat.test.tsx`
- Date: 2026-03-25 17:07 EET
- Result: pass (`6 passed`)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifact_coding_agent/chat_model.test.ts`
- Date: 2026-03-25 17:53 EET
- Result: pass (`5 passed`)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifact_coding_agent/useArtifactCodingChat.test.tsx`
- Date: 2026-03-29 Asia/Hebron
- Result: pass (`3 passed`)

## Known Gaps

- copied artifact chat UI still needs dedicated frontend tests
- hook-level streaming tests still need coverage for terminal event handling
