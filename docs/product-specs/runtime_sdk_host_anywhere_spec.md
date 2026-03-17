# Runtime SDK Host-Anywhere Spec

Last Updated: 2026-03-17

This document is the canonical runtime SDK contract for externally hosted published-app clients.

This package is not the embedded-agent SDK. For agent embedding into a customer-owned app without creating a published app, use the embedded-agent runtime and `@talmudpedia/embed-sdk` instead.

## Purpose

The runtime SDK provides a stable client contract for:
- fetching runtime bootstrap data
- streaming runtime chat events
- handling published-app auth flows
- supporting externally hosted published-app experiences

Hosted same-origin app runtime remains on the app host `/_talmudpedia/*` surface and is not the primary browser contract for host-anywhere clients.

## Current Package Shape

Current package path:
- `packages/runtime-sdk/`

Current package name:
- `@talmudpedia/runtime-sdk`

Current exported modules:
- `core`
- `runtime`
- `auth`

## Current Client Contract

Current client shape:
- `createRuntimeClient({ apiBaseUrl, bootstrap, tokenProvider, fetchImpl })`
- `client.stream(input, onEvent) -> { chatId }`

## Current Bootstrap Contract

Current bootstrap schema version:
- `runtime-bootstrap.v1`

Current bootstrap endpoints:
- `GET /public/external/apps/{app_slug}/runtime/bootstrap`
- `GET /public/apps/preview/revisions/{revision_id}/runtime/bootstrap`

Current bootstrap payload includes:
- app identity
- runtime mode
- runtime/chat routing information
- auth capability information

Important current behavior verified in code:
- published same-origin app-host runtime remains on `/_talmudpedia/*`
- external published runtime uses the dedicated `/public/external/apps/{slug}/*` route family
- preview runtime/bootstrap endpoints are active on the public router
- preview token transport is bearer/cookie based; query-token-only auth is not supported

## Current Auth Exchange Contract

Endpoint:
- `POST /public/external/apps/{app_slug}/auth/exchange`

Purpose:
- exchange external identity for a platform-native app session token

Current backend also supports host-runtime auth-exchange handling under hosted internal routes.

## Current Integration Flow

1. Fetch bootstrap from `/public/external/apps/{slug}/runtime/bootstrap` or the preview revision endpoint.
2. Build the runtime client with the bootstrap payload.
3. Authenticate external clients through bearer-token auth routes under `/public/external/apps/{slug}/auth/*`.
4. Use the returned bearer token for chat streaming and thread/history APIs.
5. For preview iframe flows, update preview auth state without relying on query-token-only URLs.

## Canonical Implementation References

- `backend/app/api/routers/published_apps_public.py`
- `backend/app/api/routers/published_apps_host_runtime.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/services/published_app_templates.py`
- `backend/app/middleware/published_apps_cors.py`
