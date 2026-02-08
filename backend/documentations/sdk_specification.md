# SDK Specification & Architecture (v1.1)

Last Updated: 2026-02-08

This document summarizes the dynamic Python SDK behavior and auth expectations for internal secure flows.

## Architecture: Schema-Driven Discovery
`Client.connect()` loads catalogs from:
- `/admin/pipelines/catalog`
- `/agents/operators`

Node classes are generated dynamically via `NodeFactory`.

## Auth for Internal Secure Calls
For internal privileged actions, SDK clients should use short-lived delegated workload tokens.

### Token Handling
`Client` now supports a `token_provider` callback so Authorization can be refreshed per request instead of relying on a long-lived static token.

### Why
Long-running agentic workloads (workers/retries/async) require rotating short-lived credentials and scope-bound access.

## Platform SDK Artifact Behavior
`builtin/platform_sdk` now requires delegated token minting for privileged actions.
Supported sources are:
1. Runtime grant-bound mint callback from executor context (`context.auth.mint_token`).
2. Internal auth broker calls (`/internal/auth/delegation-grants` + `/internal/auth/workload-token`) when caller user token + tenant context are provided.

Removed behavior:
- No pseudo-user token mint fallback.
- No env-based privileged API key/token fallback for internal secure actions.

## Roadmap Notes
- Expand async-first client APIs for high-throughput workflows.
- Add first-class helpers for delegation grant + token mint lifecycle.
