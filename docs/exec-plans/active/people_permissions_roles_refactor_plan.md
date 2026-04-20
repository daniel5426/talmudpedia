# People Permissions Roles Refactor Plan

Last Updated: 2026-04-20

This is the living implementation plan for the people-permissions role-model refactor.

Update this file when:

- scope changes
- new codebase findings change sequencing
- a plan item starts, finishes, or is dropped
- validation finds a real blocker or follow-up

This plan tracks implementation progress. The product source of truth remains:

- `docs/product-specs/people_permissions_roles_spec.md`

## Goal

Finish the hard cut from the legacy mixed role model to the canonical V1 model:

- local Talmudpedia roles are the control-plane auth source of truth
- role families are strict: `organization` or `project`
- preset roles are:
  - org: `Owner`, `Reader`
  - project: `Owner`, `Member`, `Viewer`
- custom roles work end to end
- member management and invite flows match the spec
- legacy role semantics are removed instead of coexisting indefinitely

## Current Baseline

Completed in phase 1:

- local control-plane authorization hard cut
- role-family-aware preset seeding
- local org-role assignment on WorkOS membership sync
- org-owner implicit project authority in effective-scope resolution
- `People & Permissions` members/roles UI cut to the new org/project split
- invite defaulting to org `Reader` and project `Member`

Validated so far:

- targeted backend permissions suites pass
- targeted frontend settings/permissions suites pass

Open stabilization item:

- adjacent settings-hub backend tests still have tenant-slug test-data isolation failures unrelated to the new role model

## Plan Maintenance Rules

- Keep statuses current: `planned`, `in_progress`, `done`, `blocked`, `dropped`.
- When a step is completed, add the main code/doc/test paths touched.
- If implementation reveals a better sequence, update the plan instead of keeping stale ordering.
- Do not duplicate final product behavior here if it already lives in the canonical spec.

## Workstreams

### 1. Phase 1 Stabilization

Status: `done`

Goal:

- close remaining test drift
- remove obvious contradictions in current-state docs
- catch leftover legacy assumptions in the control-plane path

Implementation:

- fix settings-hub backend test isolation failures
- sweep for remaining old preset names in active control-plane codepaths
- update current-state docs that still describe WorkOS as the org-level authz source

Validation:

- adjacent backend settings/auth suites pass
- no control-plane path still depends on WorkOS permissions for authorization decisions

### 2. Custom Roles End To End

Status: `in_progress`

Goal:

- ship V1 custom roles, not just backend-ready contracts

Implementation:

- complete family-aware custom-role CRUD behavior and validation
- add custom-role create/edit/delete UI under `Roles`
- expose grouped permission selection by family
- enforce preset immutability in backend and frontend
- ensure assignment flows show only compatible roles

Validation:

- custom org role creation/edit/delete tests
- custom project role creation/edit/delete tests
- family-mismatch assignment rejection tests
- frontend role-editor tests

### 3. Project Access Management UX

Status: `planned`

Goal:

- make the member-management flow match the spec exactly

Implementation:

- member detail flow manages:
  - one org role
  - zero or more project memberships
  - one project role per project
- invite flow supports:
  - org membership default
  - selected projects
  - shared default project role
- surface org-owner implicit access clearly without fake project rows

Validation:

- invite acceptance persists selected project access
- member edit flows replace roles cleanly
- UI tests cover org role, project access, and inherited org-owner power

### 4. Control-Plane Enforcement Sweep

Status: `planned`

Goal:

- make the full control plane use the same local authorization model

Implementation:

- audit settings/admin routers for legacy org-role assumptions
- align frontend gating with backend effective scopes
- align auth/session payload consumers with local effective-scope resolution
- remove raw `scope_type` / `scope_id` leakage from user-facing flows where still present

Validation:

- settings/admin regression suite passes
- session/effective-scope tests prove WorkOS permission payload changes do not affect control-plane authz

### 5. Legacy Cleanup Hard Cut

Status: `planned`

Goal:

- remove blurry legacy role code instead of carrying dual models

Implementation:

- remove old preset-name branches
- remove mixed-scope assignment assumptions
- delete obsolete role-editor paths no longer used by the product
- clean legacy routers/services that still construct roles without the canonical family model except where intentionally retained

Validation:

- grep/audit confirms no active control-plane path relies on removed legacy semantics
- focused regression tests still pass after cleanup

### 6. Publish / Runtime Permission Boundary

Status: `planned`

Goal:

- enforce the spec boundary between build/preview and publish/external exposure

Implementation:

- ensure `Project Member` can build, connect, run, and preview draft resources end to end
- ensure publish/embed/external exposure and deployment-facing settings stay `Project Owner` only
- align project API key and project-member-management rules with the spec

Validation:

- permission tests for preview vs publish
- project-role tests for project settings, members, deployment, and public exposure

## Progress Log

### Done

- phase-1 control-plane authorization hard cut
- role-family schema and preset refactor
- local invite persistence bridge for project access
- `People & Permissions` UI refactor to org/project role families
- targeted backend/frontend validation for the new settings permissions path
- settings-hub slug-isolation test cleanup

### In Progress

- custom roles end to end

### Next Up

- finish custom-role UI and end-to-end assignment flows
- start project access management UX
