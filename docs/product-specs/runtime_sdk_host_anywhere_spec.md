# Runtime SDK Host-Anywhere Spec

Last Updated: 2026-03-10

This document is the canonical runtime SDK contract for published apps that run on-platform or on external hosting.

## Purpose

The runtime SDK provides a stable client contract for:
- fetching runtime bootstrap data
- streaming runtime chat events
- handling published-app auth flows
- supporting hosted and externally hosted published-app experiences

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
- `GET /public/apps/{app_slug}/runtime/bootstrap`
- `GET /public/apps/preview/revisions/{revision_id}/runtime/bootstrap`

Current bootstrap payload includes:
- app identity
- runtime mode
- runtime/chat routing information
- auth capability information

Important current behavior verified in code:
- public published runtime/bootstrap asset delivery is host-runtime-only in the public router and may defer to hosted runtime handling
- preview runtime/bootstrap endpoints are active on the public router
- preview token transport is bearer/cookie based; query-token-only auth is not supported

## Current Auth Exchange Contract

Endpoint:
- `POST /public/apps/{app_slug}/auth/exchange`

Purpose:
- exchange external identity for a platform-native app session token

Current backend also supports host-runtime auth-exchange handling under hosted internal routes.

## Current Integration Flow

1. Fetch bootstrap for the published app slug or preview revision.
2. Build the runtime client with the bootstrap payload.
3. Provide a token provider for platform bearer/session usage when needed.
4. For preview iframe flows, update preview auth state without relying on query-token-only URLs.
5. If using external identity, exchange the external token for a platform app session.

## Canonical Implementation References

- `backend/app/api/routers/published_apps_public.py`
- `backend/app/api/routers/published_apps_host_runtime.py`
- `backend/app/services/published_app_auth_service.py`
- `backend/app/services/published_app_templates.py`
- `backend/app/middleware/published_apps_cors.py`
