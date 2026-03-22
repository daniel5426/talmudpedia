# Standalone Export

Last Updated: 2026-03-22

Generated export for a Talmudpedia classic-chat app.

## Local Development

```bash
pnpm install
pnpm dev
```

This starts:

- Vite on `http://127.0.0.1:5173`
- local API shim on `http://127.0.0.1:3001`

## Vercel Deployment

Set these environment variables:

- `TALMUDPEDIA_BASE_URL`
- `TALMUDPEDIA_EMBED_API_KEY`
- `TALMUDPEDIA_AGENT_ID`
- `SESSION_COOKIE_SECRET`

Then deploy the repo to Vercel. The frontend is built by Vite and `/api/*` is served by the included serverless handlers.
