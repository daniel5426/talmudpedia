# Railway Launch Runbook

Last Updated: 2026-03-23

This is the canonical runbook for launching the core Talmudpedia platform on Railway.

## Topology

Create one Railway project with these services:

- `frontend`
  - Root directory: `frontend-reshet/`
  - Config in `frontend-reshet/railway.toml`
- `backend`
  - Root directory: `backend/`
  - Config in `backend/railway.toml`
  - Pre-deploy command: `./scripts/railway_predeploy.sh`
- `backend-worker`
  - Root directory: `backend/`
  - Start command: `./scripts/start_celery_worker.sh`
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

Use `backend/railway.env.example` as the source template.

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

Use `frontend-reshet/railway.env.example` as the source template.

Required values:

- `NEXT_PUBLIC_BACKEND_URL`
- `NEXT_PUBLIC_BACKEND_STREAM_URL`
- `NEXT_PUBLIC_APPS_BASE_DOMAIN`
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` only if Google auth is enabled

## Service Notes

### Backend

- Railway healthcheck path is `/health`.
- Run migrations before each deploy with `./scripts/railway_predeploy.sh`.
- `backend/Procfile` remains the canonical uvicorn command source.

### Worker

- Use `./scripts/start_celery_worker.sh`.
- Default queues:
  - `default`
  - `ingestion`
  - `embedding`
  - `apps_build`
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
8. Attach platform domains:
   - main platform/admin host
   - API host
   - wildcard `*.apps.<domain>` for published apps
9. Publish one app and verify host-based runtime.
10. Run one `web_crawler` smoke test and one published-app smoke test.

## Validation Checklist

- backend health endpoint responds
- migrations complete successfully
- worker consumes tasks
- admin frontend can authenticate and call backend
- published apps resolve correctly on wildcard subdomains
- R2 bundle reads/writes work
- Sprite-backed app-builder runtime still works from Railway backend
- Cloudflare artifact runtime still works from Railway backend
- Crawl4AI-backed pipeline execution succeeds
- if pgvector is used, extension creation and retrieval succeed
