# Deployment Spec

Last Updated: 2026-04-19

This document is the canonical source of truth for the live Railway deployment state.

## Scope

This describes the current deployed platform, not an intended future state.

- Railway project: `lavish-optimism`
- Environments:
  - `production`
  - `staging`

For the release process, see [docs/references/railway_staging_first_release_workflow.md](/Users/danielbenassaya/Code/personal/talmudpedia/docs/references/railway_staging_first_release_workflow.md).

## Live Production Topology

Repo-backed application services:

- `frontend`
  - root: `frontend-reshet/`
  - primary public host: `https://agents24.dev`
- `backend`
  - root: `backend/`
  - primary public host: `https://api.agents24.dev`
- `backend-worker`
  - Docker-backed worker service
  - Dockerfile: [`deploy/backend-worker/Dockerfile`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/backend-worker/Dockerfile)
  - start command: `./scripts/start_celery_worker.sh`
- `docs-site`
  - root: `docs-site/`
  - public host: `https://docs.agents24.dev`
- `crawl4ai`
  - root: `deploy/crawl4ai/`
  - public host: `https://crawl4ai-production-6d56.up.railway.app`

Managed data services:

- `Postgres`
- `Redis`

Retired service:

- `crawl4ai-runtime`
  - deleted from the project on 2026-04-19
  - no longer part of the live topology or release path

External systems that remain outside Railway:

- Sprite
- Cloudflare Workers
- Cloudflare R2

## Current Release Model

Current release policy:

- `staging`
  - auto-deploys repo-backed app services from `main`
- `production`
  - has no GitHub auto-deploy triggers
  - is promoted manually by tested commit SHA

Repo-backed services in this release path:

- `backend`
- `frontend`
- `backend-worker`
- `docs-site`
- `crawl4ai`

## Current Domain And Runtime State

Production routing and base URLs are aligned to:

- platform frontend: `https://agents24.dev`
- platform API: `https://api.agents24.dev`
- docs: `https://docs.agents24.dev`
- published apps base domain: `apps.agents24.dev`
- crawler base URL: `https://crawl4ai-production-6d56.up.railway.app`

Current backend production env is aligned to:

- `API_BASE_URL=https://api.agents24.dev`
- `PLATFORM_BASE_URL=https://agents24.dev`
- `APPS_BASE_DOMAIN=apps.agents24.dev`
- `APPS_URL_SCHEME=https`
- `CORS_ORIGINS=https://agents24.dev,https://www.agents24.dev`
- `CRAWL4AI_BASE_URL=https://crawl4ai-production-6d56.up.railway.app`
- `DB_TARGET=production`

Current frontend production env is aligned to:

- `NEXT_PUBLIC_BACKEND_URL=https://api.agents24.dev`
- `NEXT_PUBLIC_BACKEND_STREAM_URL=https://api.agents24.dev`
- `NEXT_PUBLIC_APPS_BASE_DOMAIN=apps.agents24.dev`

Current backend-worker production env is aligned to:

- `APPS_BASE_DOMAIN=apps.agents24.dev`
- `APPS_URL_SCHEME=https`
- `CRAWL4AI_BASE_URL=https://crawl4ai-production-6d56.up.railway.app`
- `DB_TARGET=production`

## Current Verified State

As of 2026-04-19, the following production services are healthy on commit `cf630754c171536f302729163f8b826a1eda0792`:

- `backend`
- `frontend`
- `backend-worker`
- `docs-site`
- `crawl4ai`

Managed services are healthy:

- `Postgres`
- `Redis`

## Tracked Deployment Files

- [`frontend-reshet/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/railway.toml)
- [`backend/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/railway.toml)
- [`deploy/backend-worker/Dockerfile`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/backend-worker/Dockerfile)
- [`backend/scripts/start_celery_worker.sh`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/scripts/start_celery_worker.sh)
- [`docs-site/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/docs-site/railway.toml)
- [`deploy/crawl4ai/Dockerfile`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/crawl4ai/Dockerfile)
- [`deploy/crawl4ai/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/crawl4ai/railway.toml)
- [docs/references/railway_launch_runbook.md](/Users/danielbenassaya/Code/personal/talmudpedia/docs/references/railway_launch_runbook.md)
- [docs/references/railway_staging_first_release_workflow.md](/Users/danielbenassaya/Code/personal/talmudpedia/docs/references/railway_staging_first_release_workflow.md)
