# Talmudpedia Standalone

Last Updated: 2026-03-17

Standalone Vite + Express app for embedding a published Talmudpedia agent through the server-only `@talmudpedia/embed-sdk`.

## Architecture

- `src/`: Vite React frontend
- `server/`: Express BFF that owns the Talmudpedia API key
- `/api/session`: local cookie-backed user identity
- `/api/agent/*`: thread history and streaming chat routes

## Environment

Copy `.env.example` to `.env` and set:

- `TALMUDPEDIA_BASE_URL`
- `TALMUDPEDIA_EMBED_API_KEY`
- `TALMUDPEDIA_AGENT_ID`
- `SESSION_COOKIE_SECRET`
- optional `PORT`

## Local Development

```bash
pnpm install
pnpm dev
```

Vite runs the frontend and proxies `/api/*` to the Express server.

## Production

```bash
pnpm build
pnpm start
```

`pnpm start` serves both the built frontend and the API from one Node process.
