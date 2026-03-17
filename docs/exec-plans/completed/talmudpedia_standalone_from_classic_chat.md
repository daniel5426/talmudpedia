# Talmudpedia Standalone From Classic Chat

Last Updated: 2026-03-17

## Summary

Built a new root app at `talmudpedia-standalone/` by copying the `classic-chat` published-app starter and converting it into a standalone customer-owned app.

The new app is a single Node deployable with:
- Vite React frontend
- Express backend-for-frontend
- server-only `@agents24/embed-sdk`
- cookie-backed local session identity
- embedded-agent thread history and streaming chat routes under `/api`

## Key Changes

- Removed published-app runtime bootstrap and auth assumptions from the browser app.
- Replaced `@talmudpedia/runtime-sdk` usage with same-origin standalone API calls.
- Added `/api/session`, `/api/agent/threads`, `/api/agent/threads/:threadId`, and `/api/agent/chat/stream`.
- Preserved the `classic-chat` shell, sidebar, history affordance, and incremental assistant rendering.
- Added standalone app environment setup and one-process production serving through Express.

## Verification

- `pnpm install`
- `pnpm lint`
- `pnpm typecheck`
- `pnpm build`
- live standalone-server verification against a running local backend and published agent:
  - `GET /api/session`
  - `GET /api/agent/threads`
  - `POST /api/agent/chat/stream`
  - `GET /api/agent/threads/:threadId`

## Local Dev Notes

- `talmudpedia-standalone/.env` is now part of the expected local workflow.
- the standalone server now auto-loads `.env` through `dotenv`.
- when the platform backend is running directly on a local port, `TALMUDPEDIA_BASE_URL` should point to that host directly, for example `http://127.0.0.1:8026`.

## Notes

- The production build currently succeeds with a large client bundle warning from Vite because the copied AI element/code-highlighting surface pulls in heavy dependencies. This is a follow-up optimization concern, not a build failure.
