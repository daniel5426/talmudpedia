# Artifact Coding Agent Frontend Tests

Last Updated: 2026-03-25

## Scope

Track frontend coverage for the artifact page coding chat panel and artifact-specific copied chat stack.

## Test Files Present

- `chat_model.test.ts`

## Key Scenarios Intended

- right-side panel open/close behavior on the artifact page
- prompt submission sends current unsaved form state
- streamed draft snapshot updates mutate local artifact editor state
- create-mode `draft_key` continuity before first save
- history/session loading for saved artifacts and create drafts
- stop flow and pending-question flow
- terminal run completion/failure settles lingering running tool rows
- history rebuild preserves assistant text segments around tool calls
- live assistant segments can be finalized independently between tool calls

## Last Run

- Command: `pnpm test -- --runInBand src/__tests__/artifact_coding_agent/chat_model.test.ts`
- Date: 2026-03-25
- Result: pass
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/artifact_coding_agent/chat_model.test.ts`
- Date: 2026-03-25 Asia/Hebron
- Result: pass (`4 passed`)

## Known Gaps

- copied artifact chat UI still needs dedicated frontend tests
- hook-level streaming tests still need coverage for terminal event handling
