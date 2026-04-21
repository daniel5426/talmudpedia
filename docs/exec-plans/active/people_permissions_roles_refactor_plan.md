# People Permissions Roles Refactor Plan

Last Updated: 2026-04-21

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

Status: `done`

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

Status: `done`

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

Status: `done`

Goal:

- make the full control plane use the same local authorization model

Implementation:

- remove WorkOS permission payload plumbing from local control-plane auth resolution
- retire the legacy `/api/tenants/{tenant_slug}/roles|role-assignments|scope-catalog` RBAC surface
- move remaining admin user-role management off `rbacService` and onto the canonical settings people-permissions service
- align frontend permission gating with canonical scope keys only, without legacy permission-name translation
- remove remaining raw `scope_type` / `scope_id` leakage from user-facing control-plane flows where still present

Audit findings driving this phase:

- `backend/app/api/dependencies.py`
  - `get_current_principal()` still passes `bundle.permissions` into `resolve_effective_scopes()`
- `backend/app/services/workos_auth_service.py`
  - `ensure_local_bundle()` still extracts/stores WorkOS permissions in the local session bundle
- `backend/app/api/routers/rbac.py`
  - legacy duplicate RBAC API still exists and still creates roles with hard-coded `family="project"`
  - legacy assignment flow still uses tenant-style scope semantics
- `frontend-reshet/src/services/rbac.ts`
  - legacy frontend contract still targets `/api/tenants/{slug}/...`
- `frontend-reshet/src/components/admin/users-table.tsx`
  - still manages roles through the legacy RBAC API with `scope_type: "tenant"`
- `frontend-reshet/src/contexts/TenantContext.tsx`
  - still translates legacy permission names instead of treating backend effective scopes as canonical

Validation:

- settings/admin regression suite passes
- session/effective-scope tests prove WorkOS permission payload changes do not affect control-plane authz
- legacy RBAC admin users flow no longer calls `/api/tenants/{slug}/roles*`

### 5. Legacy Cleanup Hard Cut

Status: `done`

Goal:

- remove blurry legacy role code instead of carrying dual models

Implementation:

- replace `role_assignments.scope_type/scope_id/actor_type` with explicit organization-vs-project targeting through `project_id`
- refactor settings people-permissions assignment APIs to `assignment_kind` + `project_id`
- delete `app.core.rbac` and move the remaining audit/org-units/rag admin callers onto canonical scope enforcement
- remove stale legacy frontend/backend test buckets instead of keeping tombstones

Validation:

- grep/audit confirms no active control-plane path relies on removed legacy semantics
- focused regression tests still pass after cleanup

### 6. Publish / Runtime Permission Boundary

Status: `done`

Goal:

- enforce the spec boundary between build/preview and publish/external exposure

Implementation:

- ensure `Project Member` can build, connect, run, and preview draft resources end to end
- ensure publish/embed/external exposure and deployment-facing settings stay `Project Owner` only
- align project API key and project-member-management rules with the spec

Validation:

- permission tests for preview vs publish
- project-role tests for project settings, members, deployment, and public exposure

### 7. Slug Identity Removal Sweep

Status: `done`

Goal:

- hard-cut slug identity out of the touched org/project/app/auth/settings surfaces

Implementation:

- published-app public/runtime/admin identity moved to `public_id` or internal UUIDs
- auth/session/bootstrap active context stays id-only for org/project
- settings API keys moved from `project_slug` to `project_id`
- published-app preview/runtime internals moved from `app_slug` to `app_public_id`

### 8. Platform-Wide Canonical Identity Slug Hard Cut

Status: `done`

Goal:

- remove slug identity from the remaining active platform-owned control-plane surfaces

Implementation:

- completed across active admin/control-plane, runtime-support, SDK, worker, and builder surfaces
- canonical active identity is now UUIDs for internal platform objects, `public_id` for published apps, `builtin_key` for built-in tools, and `system_key` for seeded system objects

Validation:

- focused backend slug-cut regressions pass
- focused frontend slug-cut regressions pass

## Progress Log

### Done

- phase-1 control-plane authorization hard cut
- role-family schema and preset refactor
- local invite persistence bridge for project access
- `People & Permissions` UI refactor to org/project role families
- targeted backend/frontend validation for the new settings permissions path
- settings-hub slug-isolation test cleanup
- legacy cleanup hard cut with explicit `project_id` role assignments
- publish/runtime permission boundary hard cut
- slug identity hard cut for touched app/auth/settings surfaces
- remaining live runtime/SDK slug contracts cut from platform-architect contracts, execution metadata, mirrored system-artifact SDK handlers, and published runtime templates
- phase-2 slice started: seeded system agents now resolve by `system_key`, and orchestration allowlists are id-only
- phase-2 slice continued: root org units now have `system_key`, monitoring/admin payloads moved off `agent_slug`, and bootstrap/native create flows no longer take slug inputs

### In Progress

- none

### Next Up

- no active roadmap items remain in this plan


Last Updated: 2026-04-21

- 2026-04-20: implemented publish/runtime permission boundary hard cut for published apps, exposure scopes, preview-client token cleanup, public app `public_id`, and touched auth/settings id-based contract changes.

## Progress Update — 2026-04-21
- Active current-surface slug cleanup is green: runtime events now use `builtin_key`, admin monitoring uses `agent_system_key`, and frontend active org/project scoping is id-only.
- Current-surface organization route/client cut is green for org units, audit, and organization API keys.
- Targeted validation passed for backend runtime/bootstrap/settings API-key suites and frontend admin/auth/settings runtime suites.
- Remaining grep hits are now concentrated in deeper internal slug storage (`ToolRegistry.slug` for generated bindings, MCP synthetic slugs) and broad internal `tenant_id`/`Tenant` model vocabulary.
- The next remaining slug work is deeper model-column cleanup for `Tenant.slug`, `Project.slug`, `RAGPipeline.slug`, and residual internal `ToolRegistry.slug`/MCP synthetic rows, followed by the separate `tenant -> organization` naming cut.

Remaining non-goal leftovers after this cut:

- content/library and integration-catalog slugs remain as domain data and stay out of scope
- a few legacy DB columns still store opaque internal row keys under the old `slug` column name, but no active control-plane/runtime identity contract depends on slug any more
- `tenant -> organization` naming remains a separate final cleanup phase and is not part of the slug-identity hard cut

### 9. Tenant to Organization Naming Hard Cut

Status: `done`

Goal:

- remove `tenant` as the canonical current vocabulary after the slug and identity cuts are complete

Implementation:

- shared auth and token helpers now use `organization_id`
- active principal, router, service, and frontend contracts now use organization naming end to end
- ORM models were cut from `Tenant`\/`tenant_id` to `Organization`\/`organization_id`
- physical schema rename landed for core organization tables and foreign-key columns
- organization API-key service/router naming replaced the remaining active tenant API-key surface
- active backend and frontend code now grep-clean for `Tenant`, `tenant_id`, `tenant_*`, and `X-Tenant-ID`

Validation:

- Alembic upgrade passed after the schema rename migration
- backend rename regression batch passed (`52 passed`)
- focused backend auth\/settings\/monitoring batch passed (`13 passed`)
- focused frontend rename regression batch passed (`11 suites passed, 25 tests passed`)

## Progress Update — 2026-04-21
- The end-to-end `tenant -> organization` hard cut is complete for active backend, frontend, router, runtime, and schema surfaces.
- Remaining `tenant` or `slug` references are limited to legacy tests, historical docs, generated artifacts, or out-of-scope domain data, not active platform identity.
