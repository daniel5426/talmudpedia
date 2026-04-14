# Embed SDK Tests

Last Updated: 2026-04-13

Scope:
- TypeScript `@agents24/embed-sdk` transport, protocol, and server-only runtime behavior.

Test files present:
- embedded_agent_sdk.test.ts

Key scenarios covered:
- Bearer API-key auth and correct `Accept` headers are attached to embed requests.
- `streamAgent` normalizes `baseUrl`, parses `run-stream.v2` SSE envelopes, and returns `X-Thread-ID`.
- Thread list/detail helpers serialize required external-user query params.
- Thread detail payloads expose canonical persisted `response_blocks` for assistant rendering.
- Embed SDK types accept explicit canonical `ui_blocks` response blocks in thread history and stream payloads.
- Wrong-version SSE envelopes raise protocol errors.
- HTTP, text-body, and network failures map to typed SDK errors.
- Browser runtime instantiation is rejected.

Last run command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/runtime_sdk/runtime_sdk_core.test.ts src/__tests__/embed_sdk/embedded_agent_sdk.test.ts`
Last run date/time: 2026-04-13 Asia/Hebron
Last run result: pass (`2 suites, 13 tests`)

Known gaps / follow-ups:
- Add published npm install smoke coverage after the first public release is live.
