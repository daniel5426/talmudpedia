# People Permissions Roles V1 Migration Plan

Last Updated: 2026-04-20

This document defines the V1 migration strategy for moving existing organizations onto the canonical role model in `docs/product-specs/people_permissions_roles_spec.md`.

This is a rollout/migration document, not the product source of truth.

## Goal

Move all existing organizations to the new role model with the simplest possible hard cut.

Current constraint:

- existing users are internal and controlled
- preserving nuanced legacy role semantics is not required
- the migration should optimize for correctness and simplicity over historical fidelity

## Migration Strategy

Use a hard cut.

For every existing organization:

- seed the canonical preset roles
- remove legacy role assignments that do not match the new model
- assign every current org member maximum access
- start using the new defaults for all future invites and project-access changes

## Canonical Cutover Rule

Every current organization member becomes:

- `Organization Owner`

No attempt is made to preserve old distinctions such as:

- legacy org admin vs member
- legacy project owner vs editor vs viewer
- legacy mixed-scope RBAC assignments

This is intentional.

`Organization Owner` already has effective organization-wide governance and project-management authority in the new spec, so promoting all current users to org owner is sufficient for V1 migration.

## Role Data Treatment

During migration:

- preset organization roles are recreated or reconciled to the canonical V1 set
- preset project roles are recreated or reconciled to the canonical V1 set
- legacy system-role variants are removed or replaced
- legacy custom roles may be discarded
- legacy role assignments may be discarded

After migration:

- all migrated users should have `Organization Owner`
- project-specific access rows are no longer required for those migrated users to retain effective access

If preserving some project-role rows helps the UI later, that can be done as a follow-up cleanup, not as a requirement for the cutover.

## Post-Migration Defaults

After the hard cut:

- new organization creator -> `Organization Owner`
- new invited or added org member -> `Organization Reader`
- new project creator -> `Project Owner`
- new project access without explicit selection -> `Project Member`

This means migration users get temporary maximum access, while all future user-management flows follow the new canonical defaults.

## Recommended Migration Steps

1. Backup current role and assignment tables.
2. Seed the new preset roles for every organization.
3. Remove legacy role assignments that do not fit the new model.
4. Assign `Organization Owner` to every current organization member.
5. Leave project-role rows optional for migrated users.
6. Switch the UI and API flows to the new default assignment rules.

## Non-Goals

- preserving exact historical RBAC intent
- translating every legacy custom role into a new custom role
- preserving every existing project-role row
- supporting dual old/new role models during rollout

## Acceptance Criteria

- every existing internal user can still do everything after cutover
- no existing internal user is blocked from building, previewing, publishing, or managing projects
- all new invites and new assignments follow the canonical V1 role spec
- the system no longer depends on the old mixed role model after migration
