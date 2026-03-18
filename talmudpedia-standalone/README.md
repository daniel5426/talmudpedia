# Talmudpedia Standalone

Last Updated: 2026-03-18

Standalone Vite + Express app for embedding a published Talmudpedia agent through the server-only `@agents24/embed-sdk`.

Important rule:
- this app is intentionally treated as a real customer standalone app
- `server/` must use `@agents24/embed-sdk` and the public embed surface only
- do not add direct admin/internal platform API calls here as workarounds for missing embed-SDK capabilities
- missing capabilities should be fixed in the public embed API and `@agents24/embed-sdk` first

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
- `TALMUDPEDIA_ADMIN_BEARER_TOKEN` for provisioning
- `TALMUDPEDIA_TENANT_ID` for provisioning
- `SESSION_COOKIE_SECRET`
- optional `PORT`
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

Vite runs the frontend and proxies `/api/*` to the Express server.

## PRICO Demo Provisioning

To create the five local HTTP tools and the published PRICO demo agent in the platform:

```bash
pnpm provision:prico-demo
```

The script prints the created agent id. Set `TALMUDPEDIA_AGENT_ID` in `.env` to that value before running the standalone app.

## PRICO Demo Runtime

The standalone server now hosts:

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
pnpm start
```

`pnpm start` serves both the built frontend and the API from one Node process.
