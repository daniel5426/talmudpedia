# Embed SDK Release Runbook

Last Updated: 2026-03-19

Use this when releasing `@agents24/embed-sdk`.

## Normal Path

1. Push SDK package changes to `main`.
2. `embed-sdk-release` automatically decides the next version from npm state and publishes directly.
3. If `packages/embed-sdk/package.json` was auto-bumped for publish, the workflow commits that version bump back to `main`.

## GitHub Requirements

- `embed-sdk-release` now publishes directly from `main`.
- Commit titles no longer control SDK release behavior.
- The workflow runs automatically only when `packages/embed-sdk/**` changes on `main`.
- Both SDK workflows also support manual `workflow_dispatch`.

## npm Requirements

- The publisher must be logged into npm on the correct account:

```bash
npm whoami
npm org ls agents24
```

- For local fallback/manual publish, disable provenance:

```bash
cd /Users/danielbenassaya/Code/personal/talmudpedia/packages/embed-sdk
npm publish --access public --no-provenance
```

- Provenance should remain enabled in GitHub Actions trusted publishing.

## Before Publishing

Preferred local preflight:

```bash
bash /Users/danielbenassaya/Code/personal/talmudpedia/packages/embed-sdk/scripts/run-local-release-checks.sh
```

This mirrors the current `embed-sdk-ci` workflow checks in one command.

Push everything and dispatch both SDK workflows from local:

```bash
bash /Users/danielbenassaya/Code/personal/talmudpedia/packages/embed-sdk/scripts/commit-push-and-run-workflows.sh
```

Use a custom commit message:

```bash
bash /Users/danielbenassaya/Code/personal/talmudpedia/packages/embed-sdk/scripts/commit-push-and-run-workflows.sh "save work and run sdk workflows"
```

Force a manual patch publish on the dispatched release workflow:

```bash
FORCE_PUBLISH=true bash /Users/danielbenassaya/Code/personal/talmudpedia/packages/embed-sdk/scripts/commit-push-and-run-workflows.sh
```

Tooling split in that script:
- `packages/embed-sdk`: `npm`
- `frontend-reshet`: `pnpm`
- `backend`: `pip` + `pytest`

`frontend-reshet` is standardized on `pnpm`. Do not regenerate or commit a `package-lock.json` there.

The script performs a clean reinstall in `frontend-reshet` before running the Jest check so stale local `node_modules` state does not break the preflight.

Run:

```bash
cd /Users/danielbenassaya/Code/personal/talmudpedia/packages/embed-sdk
npm install
npm run build
npm run smoke:pack
```

Verify the package version:

```bash
cat /Users/danielbenassaya/Code/personal/talmudpedia/packages/embed-sdk/package.json | grep '"version"'
```

## Common Failure Modes

### Release PR was not created

- This runbook no longer uses release PRs.

Fix:
- use the direct publish workflow on `main`
- or dispatch `embed-sdk-release` manually

### Local publish fails with provenance error

Cause:
- provenance is enabled in `package.json`, but local publish is not running in supported CI

Fix:
- use `npm publish --access public --no-provenance`

### Local publish fails with `404` on scoped package

Cause:
- npm user is not authenticated correctly, or
- npm user does not have permission on the `@agents24` scope

Fix:

```bash
npm logout
npm login
npm whoami
npm org ls agents24
```

### `pnpm add @agents24/embed-sdk@<version>` cannot find the new version

Cause:
- npm registry metadata has not propagated yet

Fix:

```bash
pnpm view @agents24/embed-sdk versions
npm view @agents24/embed-sdk versions --registry=https://registry.npmjs.org/
```

Wait until the version appears, then install it.
