# Talmudpedia Standalone

Last Updated: 2026-03-21

Standalone Vite app with Vercel-compatible serverless BFF routes for embedding a published Talmudpedia agent through the server-only `@agents24/embed-sdk`.

Important rule:
- this app is intentionally treated as a real customer standalone app
- `api/` and server-side scripts must use `@agents24/embed-sdk` and the public embed surface only
- do not add direct admin/internal platform API calls here as workarounds for missing embed-SDK capabilities
- missing capabilities should be fixed in the public embed API and `@agents24/embed-sdk` first

## Architecture

- `src/`: Vite React frontend
- `api/`: Vercel function handlers for the thin BFF
- `server/`: shared server-only helpers and provisioning scripts
- `/api/session`: local cookie-backed user identity
- `/api/agent/*`: thread history and streaming chat routes
- `/api/prico-tools/*`: local demo tool endpoints for the PRICO showcase

## Environment

Copy `.env.example` to `.env` and set:

- `TALMUDPEDIA_BASE_URL`
- `TALMUDPEDIA_EMBED_API_KEY`
- `TALMUDPEDIA_AGENT_ID`
- `TALMUDPEDIA_ADMIN_BEARER_TOKEN` for provisioning
- `TALMUDPEDIA_TENANT_ID` for provisioning
- `SESSION_COOKIE_SECRET`
- optional `PRICO_TOOL_BASE_URL`
- optional `PRICO_AGENT_MODEL_ID`
- optional `PRICO_DB_HOST`
- optional `PRICO_DB_PORT`
- optional `PRICO_DB_USER`
- optional `PRICO_DB_PASSWORD`
- optional `PRICO_DB_DATABASE`

## Local Development

```bash
pnpm install
pnpm dev
```

`pnpm dev` starts:

- Vite on `http://127.0.0.1:5173`
- a small local Node API shim on `http://127.0.0.1:3001`

The Vite dev server proxies `/api/*` to the local API shim. This keeps local development on normal Vite while still exercising the same `api/` route modules used by Vercel deployment.

If you want to run them separately:

```bash
pnpm dev:api
pnpm dev:client
```

## PRICO Demo Provisioning

To create the five local HTTP tools and the published PRICO demo agent in the platform:

```bash
pnpm provision:prico-demo
```

The script prints the created agent id. Set `TALMUDPEDIA_AGENT_ID` in `.env` to that value before running the standalone app.

## PRICO Demo Runtime

The standalone Vercel functions now host:

- `/api/prico-tools/*` read-only demo endpoints for the five PRICO tool contracts
- live SQL-backed PRICO reads when `PRICO_DB_*` is configured locally
- local session state with a selected demo client
- chat forwarding that injects selected client context into the embedded-agent request

## Showcase Data Seed

To seed a clean PRICO showcase dataset into the local SQL Server:

```bash
pnpm seed:prico-showcase
```

This inserts three curated demo clients plus clean deals, currency mappings, `paku` rows, and market benchmarks.

## Production

```bash
pnpm build
```

For a local production-style frontend preview only:

```bash
pnpm preview
```

## Deploy To Vercel

This app is now structured for direct deployment from `talmudpedia-standalone/`:

```bash
pnpm install
pnpm dlx vercel
```

For production deploys:

```bash
pnpm dlx vercel --prod
```

Required Vercel project environment variables:

- `TALMUDPEDIA_BASE_URL`
- `TALMUDPEDIA_EMBED_API_KEY`
- `TALMUDPEDIA_AGENT_ID`
- `SESSION_COOKIE_SECRET`
- optional `PRICO_DB_*`
- optional `PRICO_TOOL_BASE_URL`

Deployment behavior:

- Vite builds to `dist/`
- `vercel.json` serves `dist/` as the static output
- `api/` contains the deployed serverless handlers
- all non-`/api/*` routes rewrite to `index.html`
- local development does not depend on `vercel dev`

## Known Limits

- `POST /api/agent/chat/stream` uses a Vercel streaming function and preserves SSE semantics. `X-Thread-ID` is best-effort because the thread id is only known after the embed stream starts, so the frontend must continue reading `run.accepted` events as the source of truth.
- `POST /api/agent/attachments/upload` uses `request.formData()` in a serverless function. Large uploads remain subject to Vercel request/body limits and have not been validated against very large files or all content types.
