# Railway Launch Runbook

Last Updated: 2026-04-10

This is the canonical runbook for launching the core Talmudpedia platform on Railway.

## Topology

Create one Railway project with these services:

- `frontend`
  - Root directory: `frontend-reshet/`
  - Config in `frontend-reshet/railway.toml`
- `docs-site`
  - Root directory: `docs-site/`
  - Config in `docs-site/railway.toml`
- `backend`
  - Root directory: `backend/`
  - Config in `backend/railway.toml`
  - Dockerfile in `backend/Dockerfile`
  - Pre-deploy command: `./scripts/railway_predeploy.sh`
- `backend-worker`
  - Root directory: `deploy/backend-worker/`
  - Config in `deploy/backend-worker/railway.toml`
- `crawl4ai`
  - Root directory: `deploy/crawl4ai/`
  - Config in `deploy/crawl4ai/railway.toml`
- Railway PostgreSQL
- Railway Redis

Keep these systems external:

- Sprite for Apps Builder sandbox/runtime
- Cloudflare Workers for artifact runtime
- Cloudflare R2 for bundle/object storage

## Required Environment

### Backend

Use the root-level Railway import templates plus Railway UI variables.

Operational split:

- local backend env: `backend/.env.local`
- Railway shared import template: `/.env.shared`
- Railway backend import template: `/.env.backend`

Required groups:

- relational database and Redis
- `SECRET_KEY` and platform base URLs
- `APPS_BASE_DOMAIN` and published-app runtime domains
- R2 bundle storage credentials
- Crawl4AI base URL
- Sprite credentials
- Cloudflare runtime credentials
- provider keys only for providers actually used in production

Production defaults that must stay disabled:

- `BACKEND_AUTO_INFRA_BOOTSTRAP=0`
- `ARTIFACT_RUNTIME_AUTO_BOOTSTRAP=0`
- `LOCAL_CRAWL4AI_AUTO_BOOTSTRAP=0`
- `LOCAL_PGVECTOR_AUTO_BOOTSTRAP=0`
- `APPS_PUBLISH_JOB_EAGER=0`
- `APPS_PUBLISH_MOCK_MODE=0`
- `ARTIFACT_RUN_TASK_EAGER=0`

### Frontend

Use the root-level frontend Railway import template.

Operational split:

- local frontend env: `frontend-reshet/.env.local`
- Railway frontend import template: `/.env.frontend`

Required values:

- `NEXT_PUBLIC_BACKEND_URL`
- `NEXT_PUBLIC_BACKEND_STREAM_URL`
- `NEXT_PUBLIC_APPS_BASE_DOMAIN`
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` only if Google auth is enabled

### Docs Site

Use a service-local variable set for the docs service.

Required values:

- `NEXT_PUBLIC_SITE_URL=https://docs.agents24.dev`

## Service Notes

### Backend

- Railway healthcheck path is `/health`.
- Run migrations before each deploy with `./scripts/railway_predeploy.sh`.
- The backend start command is defined in `backend/railway.toml`.
- The backend is Docker-backed and includes `uv`, `wrangler`, and `pnpm` because artifact publish requests deploy Cloudflare workers directly from the API service.
- Local HuggingFace embedding support is intentionally split into `backend/requirements-local-embeddings.txt` so Railway does not download the full torch stack unless that feature is explicitly needed.

### Docs Site

- Deploy it from `docs-site/` as its own Railpack service.
- Use the Next.js start command from `docs-site/railway.toml`.
- Attach `docs.agents24.dev` as a custom domain.
- Current DNS requirements are:
  - `docs CNAME v074b16m.up.railway.app`
  - `_railway-verify.docs TXT railway-verify=4a5235637efb48029ef4968e8d5ba9a0981a5b0a43f157e5caa764979d951d34`

### Worker

- Use `./scripts/start_celery_worker.sh`.
- Deploy it from `deploy/backend-worker/` as its own Docker-backed Railway service so it does not inherit [`backend/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/railway.toml).
- Default queues:
  - `default`
  - `ingestion`
  - `embedding`
  - `apps_build`
  - `artifact_test`
  - `artifact_prod_interactive`
  - `artifact_prod_background`
- Optional:
  - set `CELERY_ENABLE_BEAT=1` if this worker should also run Celery Beat
  - override `CELERY_QUEUES` or `CELERY_LOG_LEVEL` only when needed

### Crawl4AI

- Deploy it as its own Railway service so crawler load stays isolated from API traffic.
- Point backend `CRAWL4AI_BASE_URL` at the deployed service URL.
- The platform has no in-app fallback crawler; if this service is down, `web_crawler` nodes fail explicitly.

### pgvector

- `pgvector` is not a separate product in this stack; it is PostgreSQL with the `vector` extension.
- If day-1 RAG uses `pgvector`, confirm the chosen Postgres instance allows `CREATE EXTENSION vector`.
- If Railway Postgres does not satisfy that requirement, keep primary app data on Railway Postgres and point `PGVECTOR_CONNECTION_STRING` to an external pgvector-capable Postgres.

## Deployment Sequence

1. Provision Railway Postgres and Redis.
2. Provision Cloudflare R2 and generate S3-compatible credentials.
3. Deploy Crawl4AI and confirm its health endpoint is reachable.
4. Configure backend env vars and set the backend pre-deploy command.
5. Deploy backend and verify `GET /health`.
6. Deploy worker and verify Celery connects to Redis.
7. Configure frontend env vars and deploy frontend.
8. Configure docs-site env vars and deploy docs-site.
9. Attach platform domains:
   - main platform/admin host
   - docs host
   - API host
   - wildcard `*.apps.<domain>` for published apps
10. Publish one app and verify host-based runtime.
11. Run one `web_crawler` smoke test and one published-app smoke test.

## Railway Variables Workflow

Deployment env changes are not automatic from local `.env` files.

Preferred workflow:

1. maintain local-only values in `backend/.env.local` and `frontend-reshet/.env.local`
2. maintain Railway import/reference templates in:
   - `/.env.shared`
   - `/.env.backend`
   - `/.env.backend-worker`
   - `/.env.frontend`
3. import/update those values in the Railway UI
4. review the staged variable changes in Railway
5. deploy the staged variable changes in Railway

Recommended structure:

- Shared Variables:
  - secrets and common config used by multiple services
- Service Variables:
  - service-specific values
  - reference variables such as `${{Postgres.DATABASE_URL}}`, `${{Redis.REDIS_URL}}`, and `${{ shared.SECRET_KEY }}`

Legacy helper:

- [`backend/scripts/sync_railway_env.py`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/scripts/sync_railway_env.py) can still push variables via the CLI
- treat it as optional tooling, not the primary Railway env workflow

## Validation Checklist

- backend health endpoint responds
- docs-site Railway domain responds
- migrations complete successfully
- worker consumes tasks
- admin frontend can authenticate and call backend
- published apps resolve correctly on wildcard subdomains
- R2 bundle reads/writes work
- Sprite-backed app-builder runtime still works from Railway backend
- Cloudflare artifact runtime still works from Railway backend
- Crawl4AI-backed pipeline execution succeeds
- if pgvector is used, extension creation and retrieval succeed
