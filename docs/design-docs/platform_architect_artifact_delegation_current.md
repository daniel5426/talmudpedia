# Platform Architect Artifact Delegation Current State

Last Updated: 2026-03-25

This document is now a pointer.

The old architect-only synchronous artifact delegation path has been removed. The canonical replacement is the generic async architect worker model documented in:

- `docs/design-docs/platform_architect_worker_orchestration_current.md`

Artifact coding now uses:
- `architect-worker-binding-prepare`
- `architect-worker-binding-get-state`
- `architect-worker-binding-persist-artifact`
- `architect-worker-spawn`
- `architect-worker-spawn-group`
- `architect-worker-get-run`
- `architect-worker-await`
- `architect-worker-respond`
- `architect-worker-join`
- `architect-worker-cancel`
