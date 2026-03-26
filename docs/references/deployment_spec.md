# Deployment Spec

Last Updated: 2026-03-27

This document is the canonical source of truth for the current Talmudpedia hosting and deployment state.

## Scope

This spec describes the actually deployed core platform state, not the intended end-state.

Current production host:
- Railway project: `lavish-optimism`
- Railway environment: `production`

## Current Service Topology

The current production topology is:

- `frontend`
  - host: `https://frontend-production-c45b.up.railway.app`
  - platform: Railway app service
  - source intent: `frontend-reshet/`
- `backend`
  - host: `https://web-production-fe8b5e.up.railway.app`
  - health: `GET /health`
  - platform: Railway app service
  - source root: `/backend`
- `backend-worker`
  - platform: Railway app service
  - source intent: `/deploy/backend-worker`
  - command: `./scripts/start_celery_worker.sh`
- `Postgres`
  - platform: Railway managed PostgreSQL
- `Redis`
  - platform: Railway managed Redis
- `crawl4ai`
  - intended platform: Railway app service
  - current status: not working

External infrastructure kept outside Railway:

- Sprite
  - used for Apps Builder sandbox/runtime
- Cloudflare Workers
  - used for artifact runtime
- Cloudflare R2
  - intended object storage target for bundle storage

## Current Live Status

As of the last verified Railway state on 2026-03-24:

- `backend`: `SUCCESS`
- `backend-worker`: `SUCCESS`
- `Postgres`: `SUCCESS`
- `Redis`: `SUCCESS`
- `frontend`: `FAILED`
- `crawl4ai`: `FAILED`

This means the platform is partially live:

- backend API is up
- worker infrastructure is up
- primary database and Redis are up
- frontend deployment is not currently healthy
- Crawl4AI is not currently deployed successfully

## Current Runtime Commands

Tracked service commands:

- frontend
  - from [`frontend-reshet/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/railway.toml)
  - `node_modules/.bin/next start --hostname 0.0.0.0 --port $PORT`
- backend
  - from [`backend/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/railway.toml)
  - `uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`
- backend-worker
  - from [`deploy/backend-worker/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/backend-worker/railway.toml)
  - Dockerfile: [`deploy/backend-worker/Dockerfile`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/backend-worker/Dockerfile)
  - `./scripts/start_celery_worker.sh`
- crawl4ai
  - intended from [`deploy/crawl4ai/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/crawl4ai/railway.toml)
  - current Railway service config is not aligned with this tracked config

## Current Domain State

Current Railway-generated public domains:

- frontend
  - `https://frontend-production-c45b.up.railway.app`
- backend
  - `https://web-production-fe8b5e.up.railway.app`

Not yet in place as deployed production custom-domain architecture:

- dedicated platform custom domain
- dedicated API custom domain
- wildcard published-app domain such as `*.apps.<domain>`

## Current Configuration State

### Backend

The backend currently has live Railway env wiring for:

- PostgreSQL connection
- Redis connection
- Google client ID
- provider/model credentials
- Sprite credentials
- Cloudflare credentials
- Mongo connection

The backend also currently contains deployment drift and local-development leftovers:

- `APPS_BASE_DOMAIN=apps.localhost`
- `APPS_URL_SCHEME=http`
- bundle storage endpoints still point at localhost-style storage
- artifact/bootstrap flags are not fully aligned with the intended production template

This means backend infrastructure is running, but the env set is not yet a clean final production configuration.

### Frontend

The frontend currently has live Railway env wiring for:

- `NEXT_PUBLIC_BACKEND_URL`
- `NEXT_PUBLIC_BACKEND_STREAM_URL`
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID`

The frontend still has deployment/config drift:

- `NEXT_PUBLIC_APPS_BASE_DOMAIN=apps.localhost`
- no final custom domain config

## Auth State

Current Google sign-in state:

- frontend `NEXT_PUBLIC_GOOGLE_CLIENT_ID` is set
- backend `GOOGLE_CLIENT_ID` is set
- Google Cloud OAuth client must allow the frontend Railway domain as an authorized JavaScript origin

Current known auth deployment issue:

- backend CORS behavior has been under active repair for the Railway frontend origin
- newer backend deployments were created to address this, but Railway deployment sequencing has caused rollout instability

## Database State

Primary relational database:

- Railway Postgres is the active primary DB

Vector storage:

- `PGVECTOR_CONNECTION_STRING` currently points at the same Railway Postgres instance
- this assumes Postgres is the active pgvector-capable target for current use

Migration state:

- the Alembic graph was repaired during Railway bring-up
- the backend moved past the earlier missing-table and missing-column failures

## Crawl4AI State

Current state:

- the tracked deploy files exist:
  - [`deploy/crawl4ai/Dockerfile`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/crawl4ai/Dockerfile)
  - [`deploy/crawl4ai/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/crawl4ai/railway.toml)
- the actual Railway service is still broken

Known current Railway error:

- `Could not find root directory: deploy/crawl4ai`

So Crawl4AI is part of the intended topology, but not part of the working deployed state yet.

## Frontend Runtime State

The frontend has had multiple deployment/runtime issues during bring-up:

- earlier `pnpm: command not found` due wrong start command
- later route-specific runtime issues around heavy client-only editor/compiler dependencies

Current code changes already made in repo:

- frontend start command corrected in [`frontend-reshet/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/railway.toml)
- agents page lazy-loads export dialog to avoid eager editor imports:
  - [`frontend-reshet/src/app/admin/agents/page.tsx`](/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/admin/agents/page.tsx)
- playground page lazy-loads React artifact pane to avoid eager compiler/editor imports:
  - [`frontend-reshet/src/app/admin/agents/playground/page.tsx`](/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/admin/agents/playground/page.tsx)

Despite that, the latest verified Railway service status for `frontend` is currently `FAILED`, so frontend deployment remains unstable.

## Tracked Deployment Files

Current tracked deployment files in repo:

- [`frontend-reshet/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/railway.toml)
- [`frontend-reshet/railway.env.example`](/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/railway.env.example)
- [`backend/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/railway.toml)
- [`backend/railway.env.example`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/railway.env.example)
- [`backend/scripts/railway_predeploy.sh`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/scripts/railway_predeploy.sh)
- [`backend/scripts/start_celery_worker.sh`](/Users/danielbenassaya/Code/personal/talmudpedia/backend/scripts/start_celery_worker.sh)
- [`deploy/crawl4ai/Dockerfile`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/crawl4ai/Dockerfile)
- [`deploy/crawl4ai/railway.toml`](/Users/danielbenassaya/Code/personal/talmudpedia/deploy/crawl4ai/railway.toml)
- [`docs/references/railway_launch_runbook.md`](/Users/danielbenassaya/Code/personal/talmudpedia/docs/references/railway_launch_runbook.md)

## Env File Workflow

Use two separate env file classes:

- local runtime
  - backend: `backend/.env.local`
  - frontend: `frontend-reshet/.env.local`
- deployment sync source
  - backend: `backend/.env.railway`
  - frontend: `frontend-reshet/.env.railway`

Rules:

- local files are for local development only
- `.env.railway` files are the intended source for Railway-managed deployed variables
- changing local env files does not change Railway
- changing `.env.railway` files does not change Railway until sync is run

Backend local env loading now prefers:

1. `backend/.env.local`
2. `backend/.env`

Deployment sync command:

```bash
python3 backend/scripts/sync_railway_env.py --sync-worker
```

That command:

- syncs `backend/.env.railway` into `backend`
- syncs `backend/.env.railway` into `backend-worker` when `--sync-worker` is used
- syncs `frontend-reshet/.env.railway` into `frontend`

Safe verification mode:

```bash
python3 backend/scripts/sync_railway_env.py --sync-worker --dry-run
```

## Known Drift From Intended Production Spec

The current deployment does not yet match the intended launch runbook in these ways:

- frontend is not currently healthy
- Crawl4AI is not deployed successfully
- custom platform/API/wildcard domains are not yet configured
- app bundle storage env still contains localhost-style placeholders instead of final R2 values
- published-app domain model is not yet aligned with final production hostnames
- backend env is operational but still mixed with local/development-era values

## Current Recommendation

Treat the present deployment as:

- a partially working Railway production-staging environment for the core backend stack
- not yet a clean final production deployment spec for tenant-facing traffic

Before calling the environment production-ready, the minimum remaining items are:

1. get `frontend` back to `SUCCESS`
2. finish the backend CORS rollout cleanly for the frontend origin
3. fix the `crawl4ai` Railway service root/deploy configuration
4. replace localhost-style bundle/domain env values with final production values
5. attach final custom domains
