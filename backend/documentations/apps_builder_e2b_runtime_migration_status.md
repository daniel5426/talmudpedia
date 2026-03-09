Last Updated: 2026-03-08

# Apps Builder E2B Runtime Migration Status (Archived)

## Status

This doc is now historical only.

App Builder is no longer active on E2B.

Current hard-cut state:
- App Builder draft runtime is Sprite-first.
- One persistent shared Sprite exists per app.
- User draft-dev sessions are attachment records to the shared app workspace.
- Coding-agent batching is app-wide shared-batch scope.
- E2B backend code remains in-repo but is archived for App Builder runtime selection.

## Why This File Still Exists

It records that E2B was the previous App Builder migration target and is intentionally retained as archived context because the E2B backend implementation still exists in the repo.

## Current Canonical References

- `backend/documentations/sandbox_spec.md`
- `backend/documentations/Plans/AppsBuilder_Current_Implementation_Overview.md`
- `backend/documentations/summary/CustomCodingAgent.md`
- `backend/documentations/apps_builder_sprite_hard_cut_status.md`

## Legacy Note

Artifacts may still use a different substrate later, but that is no longer tied to App Builder draft runtime selection.
