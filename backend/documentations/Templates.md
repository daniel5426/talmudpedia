# Templates

Last Updated: 2026-03-15

## Current State Summary
- This file is now a legacy reference for published-app template state.
- The old template catalog (`chat-classic`, `chat-grid`, `chat-editorial`, `chat-neon`, `chat-soft`, `fresh-start`) was removed from the repo.
- A new starter project now exists at `backend/app/templates/published_apps/classic-chat/`.
- The canonical template-pack key for that starter is `classic-chat`.
- `classic-chat` now includes a modular chat-first base page that mirrors the playground shell and uses AI elements/shadcn primitives as its primary building blocks.
- The backend template loader/bootstrap plumbing still exists, and the current direction is a single canonical starter rather than a restored broad catalog.
- Use `docs/design-docs/apps_builder_current.md` and `docs/references/classic_chat_template_reference.md` for current canonical template/app-builder detail.

## What Still Exists

- Loader/service entry point: `backend/app/services/published_app_templates.py`
- Current starter project: `backend/app/templates/published_apps/classic-chat/`
- Bootstrap overlay sources:
  - `backend/app/templates/published_app_bootstrap/common/*`
  - `backend/app/templates/published_app_bootstrap/opencode/.opencode/*`
- Runtime SDK package source:
  - `packages/runtime-sdk/*`
- Data/API semantics that still reference templates:
  - `template_key` on app and revision records
  - admin/template-related routes that still call the template loader

## What Was Removed

- The previous checked-in published-app template catalog
- The old multi-template catalog and its design-specific guidance
- Any claim that the old catalog is still the current source of truth

## Current Starter Direction

- `classic-chat` is the fresh clean-cut replacement starter.
- Prefer a single high-quality starter over restoring a broad catalog too early.
- Keep runtime/bootstrap integration shared and minimal so visual/UI direction can evolve without rebuilding platform contracts.
- Current dependency and component inventory lives in `docs/references/classic_chat_template_reference.md`.

## Dependency Policy (Builder Validation)
- Enforced by: `backend/app/services/apps_builder_dependency_policy.py`
- Policy currently validates project/package shape and import safety (not curated package allowlisting).
- Import rules currently enforced:
  - local relative imports (`./`, `../`) allowed
  - alias imports (`@/...`) allowed
  - `node:` imports allowed
  - network imports (`http(s)://`) blocked
  - absolute imports (`/foo/bar`) blocked
  - package imports are not allowlist-restricted by this validator.

## Runtime/Preview State Relevant To Templates
- Preview runtime now returns preview URL based on built manifest entry HTML (`.../assets/{entry_html}`) and appends a preview token.
- Preview auth bridge supports:
  - bearer token
  - `preview_token` query param
  - `published_app_preview_token` cookie
- Result: built template previews can load `index.html` + JS assets when opened from builder preview flow.
- Template `runtime-sdk.ts` resolves runtime bootstrap by explicit contract (inline runtime context, runtime bootstrap endpoint, or injected config), not URL-path inference.
- Runtime bootstrap endpoints are canonicalized:
  - `GET /public/apps/{slug}/runtime/bootstrap`
  - `GET /public/apps/preview/revisions/{revision_id}/runtime/bootstrap`
- Runtime HTML payloads inject `window.__APP_RUNTIME_CONTEXT` using the same bootstrap schema used by the endpoints.
- Preview chat stream calls continue to support preview token bridging.

## Operational Notes

- For local testing through the builder, backend + worker must be running and using latest code.
- If a new template pack is introduced, validate it against the shared dependency policy and runtime/bootstrap overlay instead of reviving old template-specific assumptions from this file.
