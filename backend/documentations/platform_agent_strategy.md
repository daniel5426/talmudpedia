# Platform Architect Agent: Strategy & Design (v2)

Last Updated: 2026-02-08

## Vision
Build a multi-agent Platform Architect that designs, drafts, and tests platform assets through internal APIs with secure SaaS-grade delegation.

## Core Principles
1. API-only execution.
2. Draft-only creation by default.
3. Test-first orchestration.
4. Delegated workload identity for privileged internal actions.

## Runtime Auth Model for Architect
The Architect runtime no longer relies on static service secret fallback.
It uses:
1. user-initiated run context,
2. delegation grant creation,
3. short-lived delegated workload token minting,
4. scope-checked internal API calls.

For workload-initiated runs, existing delegation context is persisted on `AgentRun` and propagated to node execution so downstream artifacts/tools mint grant-bound tokens.

## Required Scopes Used by Architect Core Flow
- `pipelines.catalog.read`
- `pipelines.write`
- `agents.write`
- `tools.write`
- `artifacts.write`
- `agents.execute`
- `agents.run_tests`

## Governance
- Non-system workload principals require explicit tenant-owner/admin approval for privileged scope policies.
- Policy updates revoke active grants.
- Sensitive mutation actions (publish/delete/promote equivalents) require explicit approval decisions for workload principals.

## Security Constraints
- No browser issuance of workload tokens.
- No long-lived workload bearer tokens.
- Scope-based enforcement at internal endpoints.
- No env-based privileged auth fallback in Platform SDK artifact paths.
