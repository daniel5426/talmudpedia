# Apps Builder Live Workspace And HMR Architecture

Last Updated: 2026-04-16

This file is retained as historical context for the retired Vite dev-server/HMR preview design. The current canonical preview architecture is the static build-watch model described in `docs/design-docs/apps_builder_current.md`.

## Status

- Retired as a canonical architecture description on 2026-04-16.
- Current preview is not HMR-based. It uses one persistent Vite/Rollup watch build pipeline that promotes static dist output and keeps the last good build live.
- The shared draft-dev workspace remains the editable source of truth for manual edits and coding-agent writes.

## What Still Applies

- Each published app still has one canonical shared draft-dev workspace.
- Per-user builder sessions still attach to that shared live workspace instead of creating per-revision preview sandboxes.
- Saved draft revisions are still durable checkpoints materialized from the live workspace asynchronously.
- Publish still points at an already materialized revision and does not drive the live preview session.
- Session `revision_id` remains lineage metadata and should not replace a healthy live workspace.

## What Changed

- The preview runtime no longer uses a Vite dev server or HMR websocket transport.
- The preview proxy no longer depends on `@vite/client` websocket rewriting, HMR owner-id preservation, or Vite module-path rewrites.
- Preview freshness now comes from watch-cycle build status and promoted static output, not browser-side hot updates.
- `workspace_revision_token` and `live_workspace_snapshot` remain workspace/code freshness metadata only; they are no longer preview rebuild triggers.

## Current Expected Behavior

- Coding-agent and manual edits update the shared live workspace.
- The persistent watcher rebuilds and promotes a new static dist on source changes.
- The iframe keeps serving the last good build until a later successful promotion replaces it.
- Durable draft revisions are still materialized separately in the background.

## Related Canonical Docs

- `docs/design-docs/apps_builder_current.md`
- `docs/design-docs/coding_agent_runtime_current.md`
- `docs/product-specs/published_apps_spec.md`
