# Control SDK Tests

Last Updated: 2026-03-16

Scope:
- TypeScript embedded-agent SDK transport and SSE parsing behavior.

Test files present:
- embedded_agent_sdk.test.ts

Key scenarios covered:
- Bearer API-key auth is attached to embedded-agent stream requests.
- SSE parsing returns streamed events and `X-Thread-ID`.
- Thread list/detail helpers serialize required external-user query params.
- Non-2xx responses map to typed SDK errors.

Last run command: `cd frontend-reshet && npm test -- --runInBand src/__tests__/control_sdk/embedded_agent_sdk.test.ts`
Last run date/time: 2026-03-16 19:38 EET
Last run result: pass (`1 suite, 3 tests`)

Known gaps / follow-ups:
- Add direct server-runtime integration coverage if this SDK is moved into a standalone package.
