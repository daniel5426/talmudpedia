# Workload Delegation Auth Design

Last Updated: 2026-02-07

## Objective
Provide SaaS-safe authorization for agentic runtimes (agents/artifacts/tools/workers) performing internal privileged API actions.

## Key Components
1. `workload_principals`
2. `workload_scope_policies`
3. `delegation_grants`
4. `token_jti_registry`
5. Internal broker APIs:
- `POST /internal/auth/delegation-grants`
- `POST /internal/auth/workload-token`
- `GET /.well-known/jwks.json`

## Authorization Invariant
`effective_scopes = user_scopes ∩ approved_workload_scopes ∩ requested_scopes`

## Token Semantics
Delegated token (`token_use=workload_delegated`) includes:
- principal, tenant, grant, jti, scope, optional run and initiator actor.

## Enforcement
Migrated secure endpoints use:
- `get_current_principal`
- `require_scopes(...)`
- `ensure_sensitive_action_approved(...)` for sensitive mutations under workload principals.

## Governance
Tenant owner/admin approval is required for privileged non-system workload policies.
Policy change revokes active grants.

## Auditing
Audit records include workload context fields:
- `initiator_user_id`
- `workload_principal_id`
- `delegation_grant_id`
- `token_jti`
- `scopes`

## Group A Migration
Implemented scope enforcement for:
- catalog read (`pipelines.catalog.read`)
- pipeline create (`pipelines.write`)
- agent create (`agents.write`)
- tool create (`tools.write`)
- artifact draft create (`artifacts.write`)

## Phase 2-4 Status
- Runtime propagation implemented:
  - `AgentRun` now stores and reuses delegation context for user and workload initiated runs.
  - Node execution context carries grant/principal/initiator IDs.
  - Artifact/tool token minting enforces delegation-grant presence.
- Group B and C migration implemented for endpoint scope enforcement (mutations + execute/test routes).
- Secure dependencies cleanup completed:
  - legacy `decode_service_token` fallback removed from secure auth dependencies.
  - env-based privileged internal auth fallback removed from Platform SDK artifact secure flow.
- Approval operations now include action approval decision APIs:
  - `GET /admin/security/workloads/approvals`
  - `POST /admin/security/workloads/approvals/decide`

## Admin App Surface
- Admin workload approvals are now available directly in the app at:
  - `/admin/security` -> `Workload Approvals` tab
- UI supports:
  - Listing pending scope policies (`GET /admin/security/workloads/pending`)
  - Approve/reject scope policies
  - Listing action approvals and submitting approval decisions
