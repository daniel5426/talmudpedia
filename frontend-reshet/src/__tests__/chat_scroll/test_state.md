# Chat Scroll Frontend Tests

Last Updated: 2026-03-28

## Scope
Shared chat scroll-restoration behavior used across playground, agent builder execute chat, apps builder coding chat, and artifact coding chat.

## Test Files Present
- `frontend-reshet/src/__tests__/chat_scroll/conversation_initial_restore.test.tsx`

## Key Scenarios Covered
- Shared `Conversation` defaults to instant bottom positioning on initial history restore.
- Specific surfaces can still opt back into animated initial restore explicitly.

## Last Run
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/chat_scroll/conversation_initial_restore.test.tsx`
- Date: 2026-03-28 Asia/Hebron
- Result: pass (`2 passed`)

## Known Gaps / Follow-ups
- Add an integration assertion that a real history-loaded chat surface starts at bottom without visible follow-up animation.
