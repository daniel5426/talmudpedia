# Talmudpedia Standalone

Last Updated: 2026-03-18

Standalone Vite + Express app for embedding a published Talmudpedia agent through the server-only `@agents24/embed-sdk`.

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
- local session state with a selected demo client
- chat forwarding that injects selected client context into the embedded-agent request

## Production

```bash
pnpm build
pnpm start
```

`pnpm start` serves both the built frontend and the API from one Node process.
