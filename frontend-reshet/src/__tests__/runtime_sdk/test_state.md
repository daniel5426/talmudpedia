# Runtime SDK Frontend Tests

Last Updated: 2026-03-16

## Scope of the feature
- Runtime SDK transport behavior from template/frontend usage perspective.
- SSE stream parsing under chunked payload delivery.
- Event normalization and token-provider invocation semantics.

## Test files present
- `frontend-reshet/src/__tests__/runtime_sdk/runtime_sdk_core.test.ts`

## Key scenarios covered
- SSE parser reconstructs events across chunk boundaries and surfaces streamed token content.
- Runtime stream envelopes require `version: run-stream.v2`.
- Malformed SSE payloads are ignored without terminating stream processing.
- `tokenProvider` is invoked and bearer token is attached to stream request headers.
- Preview bootstrap fetch uses bearer header auth when preview token exists and does not append `preview_token` query params.
- Published runtime bootstrap uses the dedicated external-runtime route family.
- Published app auth/history helpers target external bearer-token routes.
- Normalized event helper falls back from `payload.content` when direct `content` is absent.

## Last run command + date/time + result
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/runtime_sdk/runtime_sdk_core.test.ts`
- Date: 2026-03-16
- Result: PASS (1 suite, 6 tests)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/runtime_sdk/runtime_sdk_core.test.ts`
- Date: 2026-03-02
- Result: PASS (1 suite, 4 tests)
- Command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps src/__tests__/runtime_sdk`
- Date: 2026-02-23
- Result: PASS (7 suites, 55 tests)
- Command: `cd frontend-reshet && npm test -- runtime_sdk`
- Date: 2026-02-22
- Result: PASS (3 passed)

## Known gaps or follow-ups
- Add auth client tests for `exchange/me/logout` flows.
- Add explicit tests for non-2xx stream error payload handling.
