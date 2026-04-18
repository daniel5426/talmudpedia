Last Updated: 2026-04-17

# Apps Builder Sprite Hard Cut Status

## Status

Sprite is now the active App Builder draft runtime substrate.

Implemented hard-cut behavior:
- `APPS_SANDBOX_BACKEND` defaults to `sprite`
- E2B is rejected for active App Builder runtime selection
- one persistent shared Sprite is owned per app
- user draft-dev sessions attach to the shared app workspace instead of owning isolated sandboxes
- preview uses the backend preview proxy against the Sprite URL
- OpenCode uses a Sprite proxy tunnel to the in-Sprite service port instead of external `:4141` URL access
- coding-agent batch scope is app-wide shared batch
- Sprite checkpoints are not used for revision/version history

## Runtime Shape

Current App Builder runtime behavior:
- live workspace is shared at app scope
- stage workspace is shared at app scope for coding-agent batches
- session stop detaches a user without destroying the Sprite
- dormant shared workspaces are swept by retention policy
- app delete destroys the Sprite provider resource

## Validation

Validated in code and tests:
- shared-workspace lifecycle unit coverage
- preview proxy provider-neutral auth coverage
- Sprite backend config coverage
- Sprite proxy tunnel coverage for OpenCode transport handshake and byte relay
- live Sprite smoke coverage for create, preview, second-editor attach, detach/reattach, provider delete recovery, and app delete cleanup
- live coding-agent e2e coverage for submit -> stream -> preview update -> draft revision materialization on the Sprite-backed shared workspace

## Remaining Follow-ups

- add live websocket/HMR coverage through the backend preview proxy
- decide whether artifact runtime remains on E2B or receives a separate Sprite-native design
