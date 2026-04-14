# Control Plane Service-First Hard Cut

Last Updated: 2026-04-14

## Summary
The control plane now moves through a service-first backend layer instead of reusing FastAPI route functions as internal execution primitives.

Adapters are now split cleanly:
- REST routers parse HTTP input, resolve auth/tenant context, call services, and serialize responses.
- Native architect-visible platform tools parse canonical tool payloads plus runtime context, call the same services, and wrap tool envelopes.
- SDKs remain external HTTP clients and are not used as internal execution paths.

## Hard Rules
- Do not call FastAPI route functions from internal control-plane runtime code.
- Do not rely on FastAPI `Query`, `Depends`, `Header`, `Request`, or route default objects inside internal service execution.
- Shared business logic belongs in plain service modules under `backend/app/services/control_plane/`.
- Runtime auth/tenant context must be passed explicitly through typed context objects, never inferred from route-only parameter state.

## Current Service Layer
This hard cut is now in place for the registry-style control-plane domains that were leaking transport concerns into native tool execution:
- models
- tools
- credentials
- knowledge stores

Shared pieces:
- `backend/app/services/control_plane/context.py`
- `backend/app/services/control_plane/errors.py`

Domain services:
- `backend/app/services/control_plane/models_service.py`
- `backend/app/services/control_plane/tool_registry_admin_service.py`
- `backend/app/services/control_plane/credentials_admin_service.py`
- `backend/app/services/control_plane/knowledge_store_admin_service.py`

## Why This Cut Was Needed
The architect `models.list` regression came from internal code calling a FastAPI route function directly and accidentally inheriting a `Query(None)` object instead of a plain value. That class of bug disappears once route adapters stop being execution cores.

The new layering fixes that by making:
- service input explicit
- runtime context explicit
- adapter behavior thin and transport-specific
- business logic transport-agnostic

## Adapter Contract
All internal control-plane execution should follow this shape:

1. Adapter resolves tenant/auth/runtime context.
2. Adapter validates and normalizes transport input.
3. Adapter calls a plain service method with explicit inputs.
4. Adapter maps service output/errors into HTTP or tool envelopes.

## Error Model
Services use shared control-plane error types for:
- validation
- not found
- conflict
- forbidden

Adapters are responsible for converting these into surface-specific envelopes while preserving the message semantics expected by the surface.

## Native Tool Impact
`backend/app/services/platform_native_tools.py` is no longer allowed to invoke router functions for the refactored registry domains. Those actions now resolve context and call the shared service layer directly.

This removes the main router-coupling bug class from native architect control-plane execution.
