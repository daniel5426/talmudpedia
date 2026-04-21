# Runtime Surface Standardization Refactor

Last Updated: 2026-04-21

## Summary

This refactor introduces a shared internal runtime-surface facade above `AgentExecutorService` and below the route layer.

The goal is to standardize lifecycle and query behavior across:
- internal `/agents/*`
- published runtime chat/thread surfaces
- embedded runtime chat/thread surfaces

External contracts remain unchanged.

## Implemented Changes

- Added `backend/app/services/runtime_surface/` with typed contracts plus shared lifecycle, event-history, and thread-detail helpers.
- Moved shared stream start/resume logic under `RuntimeSurfaceService`.
- Moved internal run-event fetch and internal cancel behavior under the same service.
- Standardized public-safe historical event generation into one helper path.
- Reused shared thread-turn serialization in published, embedded, and admin thread-detail flows.

## Route Migration Status

- Internal `/agents/{id}/stream`: migrated to the shared facade.
- Internal `/agents/runs/{run_id}/events`: migrated to the shared facade.
- Internal `/agents/runs/{run_id}/cancel`: migrated to the shared facade.
- Published app chat stream wrappers: migrated underneath existing route contracts.
- Embedded runtime chat stream: migrated underneath the existing route contract.
- Published host runtime thread list/detail routes: now use the canonical runtime-surface lifecycle/query service directly.
- Builder preview thread list/detail routes: now use the canonical runtime-surface lifecycle/query service directly.
- Published external and embedded thread list/detail/delete flows now import canonical shared serializers/helpers directly instead of legacy embed/host wrapper exports.

## Validation

- Added `backend/tests/runtime_surface_standardization/` with dedicated route regressions for:
  - stream start headers across internal/published/embed
  - paused run resume payload handling
  - internal run-event fetch and cancel behavior
  - host-runtime thread detail using the canonical public event projection path
  - public-safe history parity between published external and embedded thread detail
- Updated route-level regressions outside the dedicated slice:
  - preview thread list/detail now assert calls hit `RuntimeSurfaceService`
  - host-runtime thread detail tests now patch canonical runtime-surface event projection
  - run-control authorization tests now validate live-task interruption through `POST /agents/runs/{run_id}/cancel`

## Remaining Follow-ups

- If runtime-surface behavior expands further, add a shared run-status helper so `/agents/runs/{id}` uses the same lifecycle service directly instead of only the control-plane adapter.
