# Embedded Agent SDK Standalone Integration Guide

Last Updated: 2026-03-20

This guide describes how a customer uses `@agents24/embed-sdk` to build a standalone app around an agent created on the platform.

## Intended Architecture

The supported v1 architecture is:

- customer frontend
- customer backend
- `@agents24/embed-sdk`
- Talmudpedia embed API
- published agent

Important rule:
- the customer frontend talks only to the customer backend
- the customer backend talks to Talmudpedia
- the Talmudpedia tenant API key must never be exposed to the browser
- `@agents24/embed-sdk` must never be imported into browser code
- the customer backend should use `@agents24/embed-sdk` as its integration surface, not bypass it with direct admin/internal platform API calls

## Prerequisites

Before integration, the customer must:

1. create the agent on Talmudpedia
2. publish the agent
3. create a tenant API key with `agents.embed`
4. store the key in backend environment variables

Required backend values:

- `TALMUDPEDIA_BASE_URL`
- `TALMUDPEDIA_EMBED_API_KEY`
- the published `agent_id`

## Install

After the first public npm release is cut:

```bash
npm install @agents24/embed-sdk
```

Until that release exists, validate the package from the repo with `packages/embed-sdk` and `npm pack`.

## Backend Client Setup

```ts
import { EmbeddedAgentClient } from "@agents24/embed-sdk";

export const talmudpediaEmbedClient = new EmbeddedAgentClient({
  baseUrl: process.env.TALMUDPEDIA_BASE_URL!,
  apiKey: process.env.TALMUDPEDIA_EMBED_API_KEY!,
});
```

## Minimal Backend Route Example

```ts
import express from "express";
import { talmudpediaEmbedClient } from "./talmudpedia";

const app = express();
app.use(express.json());

app.post("/api/agent/chat", async (req, res) => {
  const { agentId, userId, input, threadId } = req.body;
  const events: Array<Record<string, unknown>> = [];

  const result = await talmudpediaEmbedClient.streamAgent(
    agentId,
    {
      input,
      thread_id: threadId,
      external_user_id: userId,
    },
    (event) => {
      events.push(event);
    },
  );

  res.json({
    threadId: result.threadId,
    events,
  });
});
```

The frontend should call `/api/agent/chat` on this customer backend. It should not call Talmudpedia directly.

## Local Development With The Repo Standalone Test App

This repo now includes a concrete standalone test app at `talmudpedia-standalone/`.

That app is useful for development and verification of the embedded-agent runtime contract because it provides:
- a Vite React frontend
- an Express backend-for-frontend
- cookie-backed local session identity
- same-origin `/api/session`, `/api/agent/threads`, `/api/agent/threads/:threadId`, and `/api/agent/chat/stream`

For local development:

1. run the Talmudpedia backend locally
2. create `talmudpedia-standalone/.env`
3. set:
   - `TALMUDPEDIA_BASE_URL`
   - `TALMUDPEDIA_EMBED_API_KEY`
   - `TALMUDPEDIA_AGENT_ID`
   - `SESSION_COOKIE_SECRET`
   - optional `PORT`
4. start the standalone app with `pnpm dev`

Important local note:
- if the backend is running directly on a local port such as `http://127.0.0.1:8026`, use that base URL directly
- do not assume a local `/api/py` prefix exists unless the backend is actually mounted behind that prefix

The current local standalone test-app flow has been verified against a running backend by:
- loading `/api/session`
- listing embedded-agent threads
- streaming a chat run through `/api/agent/chat/stream`
- reopening the resulting thread through `/api/agent/threads/:threadId`

## History Example

```ts
const threads = await talmudpediaEmbedClient.listAgentThreads(agentId, {
  externalUserId: userId,
});

const thread = await talmudpediaEmbedClient.getAgentThread(agentId, threadId, {
  externalUserId: userId,
});
```

Current boundary:

- thread detail gives final persisted turns
- each turn also includes `run_events` with ordered historical non-text `run-stream.v2` events for replaying tool and reasoning activity on old chats
- delete-thread is available through the embed public API and `@agents24/embed-sdk`
- if the standalone app needs a future missing capability, fix the public embed API and `@agents24/embed-sdk` first instead of adding a standalone-only direct platform API workaround

## Identity and Thread Rules

The customer must pass its own user identity on every call:

- `external_user_id` is required
- `external_session_id` is optional
- returned `threadId` should be stored by the customer backend/app and reused for resume/history

Thread ownership is enforced by:

- tenant
- published agent
- `external_user_id`

## Customer Implementation Flow

1. User sends a message in the customer frontend.
2. Customer frontend posts the message to the customer backend.
3. Customer backend resolves the customer’s internal user id.
4. Customer backend calls `streamAgent(...)` with:
   - `agentId`
   - `input`
   - `external_user_id`
   - optional `thread_id`
5. Talmudpedia returns streamed runtime events and `X-Thread-ID`.
6. Customer backend forwards the response to the frontend in its preferred shape.
7. Customer backend stores `threadId` and reuses it for later requests.
8. Customer backend uses thread list/detail methods for history screens.

## What Not To Do

- Do not call the embed API directly from the browser.
- Do not put the tenant API key in frontend code, local storage, cookies, or public env vars.
- Do not import `@agents24/embed-sdk` into a React app, Next client component, or any browser bundle.
- Do not use `@talmudpedia/runtime-sdk` for embedded-agent runtime.
- Do not create a published app if the product need is only “use this agent inside my existing app”.
- Do not patch `talmudpedia-standalone/` with direct calls to admin/internal Talmudpedia APIs to work around missing embed-SDK features.
