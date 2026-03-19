# Embed SDK Release Runbook

Last Updated: 2026-03-19

Use this when releasing `@agents24/embed-sdk`.

## Normal Path

1. Merge SDK changes to `main` with a releasable conventional commit, for example:
   - `fix(embed-sdk): add thread delete and turn run-events`
2. Wait for `embed-sdk-release` to run.
3. Confirm `release-please` creates or updates the release PR.
4. Merge the release PR.
5. Confirm the publish job releases the new npm version.

## GitHub Requirements

- Repo setting must allow GitHub Actions to create pull requests:
  - `Settings -> Actions -> General -> Allow GitHub Actions to create and approve pull requests`
- `embed-sdk-release` is a two-step flow:
  - push to `main`
  - merge the release PR
- A direct push to `main` does not publish the package by itself.

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

Tooling split in that script:
- `packages/embed-sdk`: `npm`
- `frontend-reshet`: `pnpm`
- `backend`: `pip` + `pytest`

The script performs a clean reinstall in `frontend-reshet` before running the Jest check so mixed `npm`/`pnpm` state in `node_modules` does not break the preflight.

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

- GitHub Actions lacks PR creation permission, or
- the merged commit was not releasable to `release-please`

Fix:
- enable PR creation in repo settings
- push a conventional commit such as `fix(embed-sdk): ...`

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
