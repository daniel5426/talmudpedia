# Embed SDK Tests

Last Updated: 2026-04-12

Scope:
- TypeScript `@agents24/embed-sdk` transport, protocol, and server-only runtime behavior.

Test files present:
- embedded_agent_sdk.test.ts

Key scenarios covered:
- Bearer API-key auth and correct `Accept` headers are attached to embed requests.
- `streamAgent` normalizes `baseUrl`, parses `run-stream.v2` SSE envelopes, and returns `X-Thread-ID`.
- Thread list/detail helpers serialize required external-user query params.
- Thread detail payloads expose canonical persisted `response_blocks` for assistant rendering.
- Wrong-version SSE envelopes raise protocol errors.
- HTTP, text-body, and network failures map to typed SDK errors.
- Browser runtime instantiation is rejected.

Last run command: `cd frontend-reshet && pnpm exec jest --runInBand src/__tests__/embed_sdk/embedded_agent_sdk.test.ts`
Last run date/time: 2026-03-19 05:01 Asia/Hebron
Last run result: pass (`1 suite, 6 tests`)

Known gaps / follow-ups:
- Add published npm install smoke coverage after the first public release is live.
