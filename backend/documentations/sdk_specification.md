# SDK Specification & Architecture (v1.2)

Last Updated: 2026-03-01

This document summarizes the current lightweight dynamic Python SDK (`backend/sdk/`) and current auth behavior in `builtin/platform_sdk`.

For the new canonical Control Plane SDK direction, see:
- `backend/documentations/platform_control_plane_sdk_spec_v1.md`

## Architecture: Schema-Driven Discovery (Current Lightweight SDK)
`Client.connect()` loads catalogs from:
- `/admin/pipelines/catalog`
- `/agents/operators`

Node classes are generated dynamically via `NodeFactory`.

## Auth for Internal Secure Calls (Current Runtime Behavior)
For privileged actions, `builtin/platform_sdk` requires delegated workload tokens.

Current implemented source:
1. Runtime grant-bound mint callback from executor context (`context.auth.mint_token`).

Not currently implemented in handler:
- direct fallback broker minting via `/internal/auth/delegation-grants` + `/internal/auth/workload-token`

Removed behavior:
- no pseudo-user token mint fallback
- no env-based privileged API key/token fallback for internal secure actions

## Roadmap Notes
- Replace current lightweight dynamic SDK with the new canonical Control Plane SDK.
- Add first-class helpers for delegation grant + token mint lifecycle in the new SDK.
