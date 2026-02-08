# Service and Workload Token Authentication

Last Updated: 2026-02-08

## Purpose
The platform now uses **delegated workload tokens** for internal runtime actions (agents, artifacts, tools, workers) that call secured internal APIs.

## Current Model
1. A workload principal is defined per tenant workload.
2. A delegation grant is created with requested scopes.
3. Effective scopes are computed by least-privilege intersection:
`initiator_user_scopes ∩ approved_workload_scopes ∩ requested_scopes`.
4. The broker issues a short-lived workload JWT (default 5 minutes).

## Token Claims
Delegated workload tokens contain:
- `iss`
- `aud`
- `sub = wp:<principal_id>`
- `tenant_id`
- `grant_id`
- `run_id` (optional)
- `scope` (array)
- `act = user:<initiator_user_id>` (optional)
- `jti`
- `iat`, `nbf`, `exp`
- `token_use = workload_delegated`

## Validation Rules
- Signature verified against workload key set (`/.well-known/jwks.json`).
- `token_use` must be `workload_delegated`.
- `tenant_id`, `grant_id`, `jti`, and scopes are required.
- `jti` must be active in `token_jti_registry`.
- Scope checks are enforced by endpoint (`require_scopes(...)`).

## Endpoint Enforcement
Delegated workload token scopes are enforced for:
- `GET /admin/pipelines/catalog` -> `pipelines.catalog.read`
- `POST /admin/pipelines/visual-pipelines` -> `pipelines.write`
- `POST /agents` -> `agents.write`
- `POST /tools` -> `tools.write`
- `POST /admin/artifacts` -> `artifacts.write`
- `PUT/PATCH/DELETE /agents/*` -> `agents.write`
- `POST /agents/{id}/publish` -> `agents.write` + sensitive approval record
- `POST /agents/{id}/validate` -> `agents.run_tests`
- `POST /agents/{id}/execute|stream|run`, `POST /agents/runs/{id}/resume` -> `agents.execute`
- `PUT /tools/{id}`, `POST /tools/{id}/publish|version`, `DELETE /tools/{id}` -> `tools.write`
- `POST /tools/{id}/publish`, `DELETE /tools/{id}` require sensitive approval record
- `PUT /admin/artifacts/{id}`, `DELETE /admin/artifacts/{id}`, `POST /admin/artifacts/{id}/promote` -> `artifacts.write`
- `DELETE /admin/artifacts/{id}`, `POST /admin/artifacts/{id}/promote` require sensitive approval record
- `PUT/DELETE /admin/pipelines/visual-pipelines/{id}`, `POST /admin/pipelines/visual-pipelines/{id}/compile` -> `pipelines.write`
- `DELETE /admin/pipelines/visual-pipelines/{id}` requires sensitive approval record

Legacy service/API-key auth is disabled for these migrated secure paths.

## Runtime Propagation
- `AgentRun` persists `delegation_grant_id`, `workload_principal_id`, and `initiator_user_id` for both user-initiated and workload-initiated runs.
- Runtime context propagates grant/principal/initiator IDs into node execution context.
- Artifact and tool executors mint scoped tokens only from an active delegation grant.

## Tenant Governance
Privileged workload scopes are governed by policy approval:
- `pending` policies cannot mint privileged tokens.
- tenant owner/admin approval moves policy to `approved` with explicit scope set.
- policy changes invalidate active grants for that principal.
- sensitive mutation routes can additionally require explicit action approvals via `/admin/security/workloads/approvals/*`.

## Security Notes
- Do not expose workload signing keys or delegated tokens to browser clients.
- Use short TTL and jti tracking for revocation.
- Keep user and workload identities distinct in audit trails.
- Legacy `decode_service_token` path is removed from secure request dependencies.
