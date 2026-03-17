# Apps Builder Live Workspace And HMR Architecture

Last Updated: 2026-03-17

This document explains the current live-workspace architecture for Apps Builder, the preview/HMR model, and the concrete failure chain that was fixed to make the draft preview behave like a real Vite dev environment.

## Final Architecture

- Each published app has one canonical draft-dev workspace.
- The draft-dev workspace is the editable source of truth for both manual builder edits and coding-agent writes.
- Builder preview is a long-lived Vite dev server running directly against that workspace.
- Per-user builder sessions attach to that shared live workspace instead of creating revision-driven preview sandboxes.
- Saved draft revisions are durable checkpoints materialized from the live workspace asynchronously.
- Publish only points at an already materialized revision and never drives the live preview session.

## Runtime Shape

The current runtime split is:

- Live editing surface:
  - shared draft-dev workspace
  - Vite dev server
  - session-scoped preview proxy
- Durable checkpoint surface:
  - workspace fingerprint
  - cached workspace build record
  - draft revision materialization
  - publish pointer

This split is intentional. Preview is fast and mutable. Revisions are durable and reproducible.

## Why The Old Behavior Was Broken

The long-tail preview bug was not one single issue. It was a chain:

1. The preview was initially still serving the old static preview service instead of the Vite dev server.
2. After the Vite dev server was correctly wired in, the websocket HMR path still was not connecting through the preview proxy.
3. After websocket transport was fixed, the live builder shell still had fallback reload behavior that caused unnecessary end-of-run reloads and white-screen flashes.
4. After the shell churn was removed, Vite updates still failed because the proxied `@vite/client` runtime was malformed for the preview path.
5. After owner-id and websocket fixes, hot-update fetches still failed because the Vite client tried to fetch `/src/...` from site root instead of through the preview proxy.
6. Root-relative asset URLs in proxied preview content also leaked outside the preview base path, which produced 404s for assets such as fonts during or after HMR-driven updates.

The practical symptom was always the same:

- the agent changed the live workspace
- the preview sometimes showed a websocket update
- but the visible app still required a manual reload

## Concrete HMR Problems That Were Fixed

The current preview proxy now has to do more than simple request forwarding.

### 1. Rewrite `@vite/client` websocket target

The Vite client must connect its websocket to the session-scoped preview path:

- `/public/apps-builder/draft-dev/sessions/{session_id}/preview/...`

It cannot use the default root websocket target because the builder preview runs behind the authenticated preview proxy.

### 2. Preserve HMR owner ids

Vite modules register hot-module ids through calls like:

- `__vite__createHotContext("/src/App.tsx")`

If proxy rewriting changes those ids to proxied URLs such as:

- `/public/apps-builder/.../preview/src/App.tsx`

then Vite update payloads for `/src/App.tsx` no longer match the browser’s registered module ids and the client logs `fetchUpdate.no_module`.

The fix was to preserve the original owner ids while still rewriting actual network import paths.

### 3. Rewrite the Vite client `base`

Even with correct websocket transport and owner ids, the Vite client can still fail if it computes hot-update fetches against:

- `/src/...`

instead of:

- `/public/apps-builder/draft-dev/sessions/{session_id}/preview/src/...`

The client base path now has to be rewritten to the preview proxy base path so dynamic HMR fetches stay inside the proxy.

### 4. Rewrite root-relative assets under the preview base path

Preview CSS and module content can still include root-relative asset references such as:

- `/node_modules/@fontsource-variable/...`

If those are not rewritten, hot-updated CSS can partially apply while fonts or other assets still 404 from site root.

## Session And Revision Rules

The live builder session follows these rules:

- reuse a healthy live draft-dev workspace whenever possible
- do not rebuild or reattach the preview just because `current_draft_revision_id` advanced
- treat session `revision_id` as lineage metadata, not as a trigger to replace the live workspace
- keep the iframe stable across token refreshes and routine session heartbeats

The durable revision path follows these rules:

- materialize only at workflow boundaries such as write-producing coding runs or manual save
- use cached workspace builds keyed by workspace fingerprint
- never rebind the live preview to the newly created revision

## Coding-Agent Relationship To The Live Workspace

- Coding-agent runs execute against the same live draft-dev workspace the preview is watching.
- Coding-agent writes update the same workspace metadata contract used by manual builder edits.
- Run finalization creates or reuses a durable revision after the run, but it does not replace the live preview workspace.

This is what makes true live preview possible:

- one workspace
- one dev server
- one preview runtime
- revisions only as checkpoints

## Current Expected Behavior

When the system is healthy:

- coding-agent changes hit the live workspace immediately
- Vite emits websocket updates for changed modules
- the iframe applies those updates without a manual reload
- a durable draft revision is created later in the background
- the next run continues from the same live workspace

## Related Canonical Docs

- `docs/design-docs/apps_builder_current.md`
- `docs/design-docs/coding_agent_runtime_current.md`
- `docs/product-specs/published_apps_spec.md`
