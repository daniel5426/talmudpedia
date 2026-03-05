# Runtime SDK v1 (Host-Anywhere)

Last Updated: 2026-02-23

## Purpose
This document defines the current runtime SDK contract for published apps that need to run both on-platform and on external hosting (GitHub/Vercel/Netlify/self-hosted).

## SDK Package
- Package path: `packages/runtime-sdk/`
- Package name: `@talmudpedia/runtime-sdk`
- Exported modules:
  - `core`: `createRuntimeClient`, SSE parsing, normalized event helpers.
  - `runtime`: `fetchRuntimeBootstrap`.
  - `auth`: published app auth client (`signup`, `login`, `exchange`, `me`, `logout`) and token store helper.

Core v1 client shape:
- `createRuntimeClient({ apiBaseUrl, bootstrap, tokenProvider, fetchImpl })`
- `client.stream(input, onEvent) -> { chatId }`

## Bootstrap Contract (Canonical)
Bootstrap schema version:
- `runtime-bootstrap.v1`

Bootstrap endpoints:
- `GET /public/apps/{app_slug}/runtime/bootstrap`
- `GET /public/apps/preview/revisions/{revision_id}/runtime/bootstrap`

Bootstrap payload includes:
- identity: `app_id`, `slug`, optional `revision_id`
- mode: `published-runtime | builder-preview`
- routing: `api_base_path`, optional `api_base_url`, `chat_stream_path`, optional `chat_stream_url`
- auth capabilities: `enabled`, `providers`, `exchange_enabled`
- preview runtime/chat URLs are tokenless; query-token transport is not supported

Runtime HTML responses inject:
- `window.__APP_RUNTIME_CONTEXT`

Injection uses the same serializer payload shape as bootstrap endpoints to prevent drift.

Preview auth transport (builder mode):
- Runtime SDK wrapper listens for `window.postMessage` auth events (`talmudpedia.preview-auth.v1`) and keeps preview token in memory only.
- Preview stream calls use `Authorization: Bearer <token>` when preview token is present.
- Preview runtime/bootstrap/assets endpoints accept bearer/cookie auth and do not accept query-token-only auth.

## Auth Exchange (External Identity -> Platform Session)
Endpoint:
- `POST /public/apps/{app_slug}/auth/exchange`

Request:
- `{ "token": "<external_oidc_jwt>" }`

Response:
- same published-app auth response shape (`token`, `token_type`, `user`)

Behavior:
- validates issuer/audience/JWKS using per-app OIDC config
- maps external identity to stable app user via `PublishedAppExternalIdentity`
- mints platform session token so chat history/stats/users remain platform-native

## Per-App CORS Model
Applied to published public endpoints under `/public/apps/{slug}/...`:
- allowlist source: `published_apps.allowed_origins` + `published_url` origin
- rejects non-allowed origins for both preflight and actual requests
- preview/resolve routes keep existing trusted-origin behavior

## Unified Bootstrap Overlay
Overlay roots:
- `backend/app/templates/published_app_bootstrap/common/`
- `backend/app/templates/published_app_bootstrap/opencode/`

Template build merge behavior (`build_template_files`):
1. template files
2. common runtime bootstrap overlay
3. `.opencode` overlay
4. `runtime-sdk/*` package files
5. app-context runtime config injection (`src/runtime-config.json`)

Template import stability:
- UI templates continue importing `./runtime-sdk`
- wrapper delegates transport to `@talmudpedia/runtime-sdk`

## External Frontend Integration (Current)
1. Fetch bootstrap (`fetchRuntimeBootstrap`) for app slug or preview revision.
2. Build client with `createRuntimeClient`.
3. Provide a `tokenProvider` for platform bearer tokens.
4. For builder preview iframe flows, push preview auth token updates over `postMessage` and keep iframe URL stable.
5. If external identity is used, exchange external JWT via `auth.exchange` and persist returned platform token.

## Backend Files of Record
- `backend/app/api/routers/published_apps_public.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/services/published_app_templates.py`
- `backend/app/middleware/published_apps_cors.py`
- `backend/app/db/postgres/models/published_apps.py`
