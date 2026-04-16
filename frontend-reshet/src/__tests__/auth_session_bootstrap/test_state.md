# Auth Session Bootstrap Tests

Last Updated: 2026-04-15

## Scope
Frontend coverage for mount-time browser session bootstrap, specifically stalled `/auth/session` requests and duplicate session refresh calls.

## Test Files
- `frontend-reshet/src/__tests__/auth_session_bootstrap/auth_service.test.ts`
- `frontend-reshet/src/__tests__/auth_session_bootstrap/auth_refresher.test.tsx`
- `frontend-reshet/src/__tests__/auth_session_bootstrap/http_client_auth_handling.test.ts`

## Key Scenarios Covered
- Concurrent `authService.getCurrentSession()` callers share a single in-flight `/auth/session` request.
- Stalled `/auth/session` requests time out instead of hanging forever.
- `AuthRefresher` preserves the current auth snapshot and flips `sessionChecked` after a session-bootstrap timeout.
- Generic non-session `401` responses no longer force a global logout.

## Last Run
- Command: `cd frontend-reshet && pnpm exec jest src/__tests__/auth_session_bootstrap/auth_service.test.ts src/__tests__/auth_session_bootstrap/auth_refresher.test.tsx src/__tests__/auth_session_bootstrap/http_client_auth_handling.test.ts --runInBand`
- Date: 2026-04-15 Asia/Hebron
- Result: PASS (`3 suites, 4 tests`)

## Known Gaps / Follow-ups
- No browser-level integration test yet for `/admin` redirect behavior after a timed-out bootstrap.
