# Railway Staging-First Release Workflow

Last Updated: 2026-04-19

This is the canonical release workflow for the Railway-hosted core platform.

## Goal

1. Work locally
2. Commit
3. Push to `main`
4. Railway auto-deploys `staging`
5. Test `staging`
6. Manually promote the same tested commit to `production`

## Current Railway Policy

- `staging`
  - GitHub deployment triggers are enabled for the repo-backed core services on branch `main`
- `production`
  - GitHub deployment triggers are disabled for the repo-backed core services
  - production deploys are manual by commit SHA

Repo-backed core services covered by this workflow:

- `backend`
- `frontend`
- `backend-worker`
- `docs-site`

Non-repo-managed data services stay outside this workflow:

- `Postgres`
- `Redis`

## Local Development

Develop locally against local env files only:

- `backend/.env.local`
- `frontend-reshet/.env.local`

Do not treat local env values as deploy inputs. Railway variables remain the deployment source of truth.

## Auto-Deploy To Staging

When you push a commit to `main`, Railway auto-deploys the repo-backed staging services above.

## Staging Validation

Before production promotion, validate at least:

- frontend loads
- auth/session flow works
- backend health responds
- worker-connected flows still run
- any feature touched by the commit works on staging

If staging is red, do not promote.

## Manual Production Promotion

Use:

```bash
scripts/railway_promote_staging_commit.sh <commit-sha>
```

The script:

- verifies `staging` is on the exact commit for each core service
- verifies those staging services are `SUCCESS`
- triggers a production deploy of that same commit SHA for:
  - `backend`
  - `frontend`
  - `backend-worker`
  - `docs-site`

Exceptional bypass:

```bash
scripts/railway_promote_staging_commit.sh <commit-sha> --skip-staging-check
```

Use that only for recovery.

## Typical Release Commands

```bash
git add <files>
git commit -m "your change"
git push origin main
```

After staging is validated:

```bash
scripts/railway_promote_staging_commit.sh <commit-sha>
```

## Operational Notes

- production must never auto-deploy from `main`
- staging is allowed to break; production is not
- production promotion must use a tested commit SHA, not an untracked local upload
- if a service is not repo-backed in Railway, it is outside this workflow until it is normalized into it

## Current Known Constraint

`crawl4ai-runtime` is still being normalized separately. The staging-first commit-promotion workflow above is currently defined for the core repo-backed platform services listed in this doc.
