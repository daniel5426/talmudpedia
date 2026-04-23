# Unified Preview Auth Contract

Last Updated: 2026-04-23

This document is the canonical preview-auth contract for published-app preview surfaces.

## Scope

The contract applies to:
- builder draft-dev preview at `/public/apps-builder/draft-dev/sessions/{session_id}/preview/...`
- published revision preview at `/public/apps/preview/revisions/{revision_id}/...`

It does not apply to end-user published-app auth. End-user runtime auth remains the separate `published_app_session` contract.

## Canonical Token

Preview auth uses one token type: `published_app_preview`.

Required claims:
- `organization_id`
- `app_id`
- `scope=["apps.preview"]`
- `preview_target_type`
  - `draft_dev_session`
  - `revision`
- `preview_target_id`

Optional claims:
- `revision_id`
- `sub`

Validation rules:
- builder preview must match `app_id + preview_target_type=draft_dev_session + preview_target_id=session_id`
- revision preview must match `app_id + preview_target_type=revision + preview_target_id=revision_id`
- if `revision_id` is present, it must also match the resolved preview target

## Canonical Cookie

Both preview surfaces use one HttpOnly cookie:
- `published_app_preview_token`

There is no separate public-preview cookie anymore.

## Bootstrap Flow

Preview bootstrap is query-once, then cookie-based:

1. Admin or preview-runtime routes return a bootstrap-ready `preview_url`.
2. That URL may contain a one-time `runtime_token` query param.
3. The first successful preview response sets `published_app_preview_token`.
4. Follow-up preview document, asset, bootstrap, chat, and status requests authenticate through the cookie.

Rules:
- the frontend treats `preview_url` as opaque
- the frontend does not manage preview-token state
- query bootstrap is allowed for first-load and refresh recovery
- cookie auth is authoritative after bootstrap

## Route Family Boundaries

Builder draft-dev preview:
- served through the builder preview proxy
- validates preview tokens against the draft-dev session target

Published revision preview:
- served through published revision preview routes
- validates preview tokens against the revision target

The route families stay separate, but they share the same token type, cookie name, and validation logic.

## Backend Responsibilities

Shared preview-auth helpers own:
- preview token issuance
- preview token decoding
- preview target matching
- preview cookie setting
- query-token bootstrap handling

Admin/session responses:
- draft-dev session responses expose only `preview_url`
- version preview-runtime responses expose only `preview_url`
- no separate `runtime_token` field is part of the public/admin response contract

## Frontend Responsibilities

Frontend preview consumers:
- use the server-provided `preview_url`
- may append route/reload/build query state
- do not append preview auth tokens manually
- do not use postMessage preview-auth channels

## Explicit Non-Goals

Preview auth does not:
- authenticate end users into the published app
- replace `published_app_session`
- grant admin access
- grant builder/project access outside the scoped preview target
