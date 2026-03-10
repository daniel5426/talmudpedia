# Auth Docs Guide

Last Updated: 2026-03-10

This file is now a legacy location for the auth guide.

For the current canonical auth entry points, read:
- `docs/design-docs/auth_current.md`
- `docs/references/auth_docs_guide.md`

This folder contains the auth-specific backend documentation.

## Read Order
1. `10_auth_current_state_overview.md`
   - Start here for the current auth model at a glance.
2. `20_auth_delegated_workload_tokens.md`
   - Read this for the current delegated workload token contract and endpoint enforcement.
3. `30_auth_workload_delegation_design.md`
   - Read this for the design rationale and governance model behind workload delegation.
4. `40_auth_published_apps_unified_gate_and_user_scope.md`
   - Read this for published-app auth, the shared auth shell, and current app-user scoping behavior.
5. `95_auth_security_unification_status_2026_03_05.md`
   - Read this for the latest implementation wave and what changed recently.

## What Each File Is About
- `10_auth_current_state_overview.md`
  - Short operational summary of the current auth types, token classes, scope enforcement, and common failures.
- `20_auth_delegated_workload_tokens.md`
  - Concrete rules for delegated workload JWTs: claims, validation, enforcement, and runtime propagation.
- `30_auth_workload_delegation_design.md`
  - Architecture/design note for workload principals, grants, approvals, and auditing.
- `40_auth_published_apps_unified_gate_and_user_scope.md`
  - Verified current behavior for published-app auth, including the unified gate and the fact that global user identity is still reused across apps.
- `95_auth_security_unification_status_2026_03_05.md`
  - Change log for the March 5 security unification wave, including RBAC and route-enforcement updates.

## Related But Not Auth-Only Docs
- `backend/documentations/Apps.md`
  - Published app product behavior lives here as part of the wider Apps feature.
- `backend/documentations/runtime_sdk_v1_host_anywhere.md`
  - Runtime SDK auth exchange and published-app auth client contract live here.
- `backend/documentations/summary/chat_thread_token_spec.md`
  - Token usage accounting and runtime auth-adjacent stream behavior live here, but this is not an auth-first doc.

## Naming Rules For Future Auth Docs
- Put auth-specific docs in `backend/documentations/auth/`.
- Prefix filenames with an order number so `ls` shows a useful reading sequence.
- Include one of these intent markers in the filename:
  - `current_state`
  - `design`
  - `status`
