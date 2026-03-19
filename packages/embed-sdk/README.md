# `@agents24/embed-sdk`

Last Updated: 2026-03-19

`@agents24/embed-sdk` is the canonical server-only TypeScript SDK for Talmudpedia embedded-agent runtime.

Use it when a customer already has its own application and wants its backend to call a published Talmudpedia agent directly through the embed API.

## Product Split

This package is not the published-app runtime SDK.

- `@talmudpedia/runtime-sdk`: browser/client SDK for published-app runtime
- `@agents24/embed-sdk`: Node/server SDK for embedded-agent runtime

## Supported Runtime

V1 is server-only.

- Node `>=18.17`
- ESM and CommonJS package exports
- built on top of native `fetch` and Web Streams

Do not use this package in browser bundles. Keep your Talmudpedia tenant API key only on your backend.

## Installation

After the first public npm release is cut:

```bash
npm install @agents24/embed-sdk
```

Until that release exists, validate the package from this repo with `npm pack` or `npm run smoke:pack`.

## Required Environment Variables

- `TALMUDPEDIA_BASE_URL`
- `TALMUDPEDIA_EMBED_API_KEY`
- published `agent_id`

The API key must have the `agents.embed` scope.

## Quickstart

```ts
import { EmbeddedAgentClient } from "@agents24/embed-sdk";

const client = new EmbeddedAgentClient({
  baseUrl: process.env.TALMUDPEDIA_BASE_URL!,
  apiKey: process.env.TALMUDPEDIA_EMBED_API_KEY!,
});

const result = await client.streamAgent(
  process.env.TALMUDPEDIA_AGENT_ID!,
  {
    input: "Summarize today’s thread.",
    external_user_id: "customer-user-123",
  },
  (event) => {
    console.log(event.event, event.payload);
  },
);

console.log(result.threadId);
```

## Architecture

Supported v1 architecture:

- customer frontend
- customer backend
- `@agents24/embed-sdk`
- Talmudpedia embed API
- published agent

The frontend talks only to the customer backend. The backend talks to Talmudpedia.

## API Reference

### `new EmbeddedAgentClient(options)`

```ts
const client = new EmbeddedAgentClient({
  baseUrl: "https://api.talmudpedia.example",
  apiKey: "tpk_live_xxx",
});
```

Options:

- `baseUrl`: base platform URL, for example `https://api.example.com`
- `apiKey`: tenant API key with `agents.embed`
- `fetchImpl`: optional custom fetch implementation for tests or custom runtimes

### `streamAgent(agentId, payload, onEvent?)`

Wraps:

- `POST /public/embed/agents/{agent_id}/chat/stream`

Payload keeps backend field names exactly:

```ts
type EmbeddedAgentStreamRequest = {
  input?: string;
  messages?: Array<Record<string, unknown>>;
  thread_id?: string;
  external_user_id: string;
  external_session_id?: string;
  metadata?: Record<string, unknown>;
  client?: Record<string, unknown>;
};
```

Returns:

```ts
type StreamAgentResult = {
  threadId: string | null;
};
```

`onEvent` receives typed `run-stream.v2` envelopes.

Current behavior:

- callback-based streaming only
- resolves after the full SSE stream is consumed
- returns `threadId` from the `X-Thread-ID` response header
- does not currently expose abort, timeout, retry, or async-iterator helpers

### `listAgentThreads(agentId, options)`

Wraps:

- `GET /public/embed/agents/{agent_id}/threads`

Options:

- `externalUserId`
- `externalSessionId?`
- `skip?`
- `limit?`

### `getAgentThread(agentId, threadId, options)`

Wraps:

- `GET /public/embed/agents/{agent_id}/threads/{thread_id}`

Options:

- `externalUserId`
- `externalSessionId?`

Returned turn shape includes:

- `id`
- `run_id`
- `turn_index`
- `user_input_text`
- `assistant_output_text`
- `status`
- `usage_tokens`
- `metadata`
- `created_at`
- `completed_at`
- `run_events`

`run_events` contains ordered historical non-text `run-stream.v2` events for that turn, intended for replaying tool, reasoning, and OpenUI UI on old chats.

Current generative UI event:

- `assistant.ui`
- current platform generative UI mode is OpenUI

Current `assistant.ui` payload fields:

- `format`
- `version`
- `content`
- `content_delta`
- `ast`
- `component_library_id`
- `surface`
- `is_final`

### `deleteAgentThread(agentId, threadId, options)`

Wraps:

- `DELETE /public/embed/agents/{agent_id}/threads/{thread_id}`

Options:

- `externalUserId`
- `externalSessionId?`

## Exact Current Surface

This package currently exposes exactly 4 runtime methods:

- `streamAgent(...)`
- `listAgentThreads(...)`
- `getAgentThread(...)`
- `deleteAgentThread(...)`

It intentionally does not expose:

- a separate run-events fetch method beyond `getAgentThread(...).turns[].run_events`
- agent/tool/admin management
- browser auth/session helpers

If you need one of those capabilities, treat it as a platform/public-embed contract change first, not just an SDK patch.

## Source Map

If you need to change the SDK in an integrated way, start from these files:

- SDK client methods: `src/client.ts`
- SDK request/response types: `src/types.ts`
- SDK SSE parsing: `src/sse.ts`
- SDK HTTP/runtime guards: `src/http.ts`
- public embed backend routes: `../../backend/app/api/routers/embedded_agents_public.py`
- backend serialization/runtime service: `../../backend/app/services/embedded_agent_runtime_service.py`

## Thread And History Usage

Pass your own application user identity as `external_user_id` on every call.

- `external_user_id` is required
- `external_session_id` is optional
- `threadId` returned from `streamAgent(...)` should be persisted by your backend and reused for resume/history

Example:

```ts
const threads = await client.listAgentThreads(agentId, {
  externalUserId: "customer-user-123",
});

const thread = await client.getAgentThread(agentId, "thread-id", {
  externalUserId: "customer-user-123",
});
```

## Error Handling

The SDK throws `EmbeddedAgentSDKError` with:

- `kind: "http" | "network" | "protocol"`
- `status` for HTTP failures
- `details` when the response body includes structured error information

```ts
import { EmbeddedAgentSDKError } from "@agents24/embed-sdk";

try {
  await client.listAgentThreads(agentId, { externalUserId: "customer-user-123" });
} catch (error) {
  if (error instanceof EmbeddedAgentSDKError) {
    console.error(error.kind, error.status, error.details);
  }
}
```

## Server-Only Warning

- Do not put the Talmudpedia API key in frontend code
- Do not store the API key in localStorage, cookies, or public env vars
- Do not call the embed API directly from the browser

## Example App

See [`examples/express-typescript/`](./examples/express-typescript/) for a minimal customer-backend integration example.

## Release Notes

This package is released through GitHub Actions using direct publish from `main` and npm trusted publishing. Local `npm pack` and `npm run smoke:pack` are the expected pre-release verification commands.
