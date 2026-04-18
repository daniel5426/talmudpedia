# Railway Launch Runbook

Last Updated: 2026-04-19

This is the canonical runbook for operating the current Railway-hosted platform.

## Active Railway Topology

One Railway project with these active services:

- `frontend`
  - root: `frontend-reshet/`
  - config: [`frontend-reshet/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/railway.toml)
- `backend`
  - root: `backend/`
  - config: [`backend/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/railway.toml)
  - predeploy: [`backend/scripts/railway_predeploy.sh`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/scripts/railway_predeploy.sh)
- `backend-worker`
  - Dockerfile: [`deploy/backend-worker/Dockerfile`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/backend-worker/Dockerfile)
  - start command: `./scripts/start_celery_worker.sh`
- `docs-site`
  - root: `docs-site/`
  - config: [`docs-site/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/docs-site/railway.toml)
- `crawl4ai`
  - root: `deploy/crawl4ai/`
  - config: [`deploy/crawl4ai/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/crawl4ai/railway.toml)
- Railway `Postgres`
- Railway `Redis`

Not active anymore:

- `crawl4ai-runtime`
  - removed from the project on 2026-04-19

## Environment Policy

Environments:

- `staging`
- `production`

Trigger policy:

- `staging`
  - auto-deploys repo-backed services from `main`
- `production`
  - manual promotion only
  - no GitHub deployment triggers

Use the release workflow in [docs/references/railway_staging_first_release_workflow.md](/Users/danielbenassaya/Code/personal/talmudpedia/docs/references/railway_staging_first_release_workflow.md).

## Required Production URL Alignment

Backend:

- `API_BASE_URL=https://api.agents24.dev`
- `PLATFORM_BASE_URL=https://agents24.dev`
- `APPS_BASE_DOMAIN=apps.agents24.dev`
- `APPS_URL_SCHEME=https`
- `CORS_ORIGINS=https://agents24.dev,https://www.agents24.dev`
- `CRAWL4AI_BASE_URL=https://crawl4ai-production-6d56.up.railway.app`
- `DB_TARGET=production`

Frontend:

- `NEXT_PUBLIC_BACKEND_URL=https://api.agents24.dev`
- `NEXT_PUBLIC_BACKEND_STREAM_URL=https://api.agents24.dev`
- `NEXT_PUBLIC_APPS_BASE_DOMAIN=apps.agents24.dev`

Backend worker:

- `APPS_BASE_DOMAIN=apps.agents24.dev`
- `APPS_URL_SCHEME=https`
- `CRAWL4AI_BASE_URL=https://crawl4ai-production-6d56.up.railway.app`
- `DB_TARGET=production`

## Service Notes

### Backend

- healthcheck path: `/health`
- migrations run before deploy via [`backend/scripts/railway_predeploy.sh`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/scripts/railway_predeploy.sh)
- production API host: `https://api.agents24.dev`

### Frontend

- production host: `https://agents24.dev`
- start command comes from [`frontend-reshet/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/railway.toml)

### Backend Worker

- isolate Celery from API traffic
- default command: `./scripts/start_celery_worker.sh`
- this service is part of the same staging-first release path as the API and frontend

### Docs Site

- production host: `https://docs.agents24.dev`
- deploy from `docs-site/` as a separate service

### Crawl4AI

- deploy as its own Railway service from `deploy/crawl4ai/`
- production crawler host: `https://crawl4ai-production-6d56.up.railway.app`
- staging crawler host: Railway-generated staging domain
- backend and worker must point to this service directly

## Deployment Sequence

For a new or repaired environment:

1. provision `Postgres` and `Redis`
2. configure service variables
3. deploy `crawl4ai`
4. deploy `backend`
5. deploy `backend-worker`
6. deploy `frontend`
7. deploy `docs-site`
8. verify custom domains and published app base domain

For day-to-day releases, do not use that sequence manually. Use the staging-first release workflow instead.

## Validation Checklist

- `staging` is green on one commit for:
  - `backend`
  - `frontend`
  - `backend-worker`
  - `docs-site`
  - `crawl4ai`
- production has no auto-deploy triggers
- production promotion uses the same tested commit SHA
- `agents24.dev` loads
- `api.agents24.dev` serves the backend
- `docs.agents24.dev` loads
- crawler requests succeed through `crawl4ai`
