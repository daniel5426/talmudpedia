# Auth Docs Guide

Last Updated: 2026-03-10

This guide lists the current auth-related entry points after the documentation refactor.

## Start Here

- `docs/design-docs/auth_current.md`
  - Canonical auth and workload-security overview.

## Focused Detailed Auth Docs

- `backend/documentations/auth/10_auth_current_state_overview.md`
  - Operational auth types and common failures.
- `backend/documentations/auth/20_auth_delegated_workload_tokens.md`
  - Concrete delegated workload-token contract and enforcement details.
- `backend/documentations/auth/30_auth_workload_delegation_design.md`
  - Workload delegation design and governance model.
- `backend/documentations/auth/40_auth_published_apps_unified_gate_and_user_scope.md`
  - Published-app auth principal and session model.
- `backend/documentations/auth/95_auth_security_unification_status_2026_03_05.md`
  - Historical implementation-wave status note.

## Related Canonical Product Specs

- `docs/product-specs/published_apps_spec.md`
- `docs/product-specs/runtime_sdk_host_anywhere_spec.md`

## Usage Rule

- Use `docs/design-docs/auth_current.md` when you need the current platform auth picture.
- Use the `backend/documentations/auth/` files when you need detailed contracts or historical implementation context.
