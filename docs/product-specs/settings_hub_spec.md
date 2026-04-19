# Settings Hub Spec

Last Updated: 2026-04-19

This document is the canonical product/specification overview for the unified settings governance surface.

For browser sign-in, active org/project context, organization creation, project creation, and invite acceptance workflow, see:

- `docs/product-specs/organization_and_project_workflow_spec.md`

## Purpose

`/admin/settings` is the single control-plane entry point for:
- organization settings
- personal profile settings
- people and permissions
- project governance
- API keys
- limits
- audit logs
- integrations
- MCP servers

Old standalone organization, security, and audit pages are removed from the intended frontend IA.

## Canonical Top-Level Tabs

- `Organization`
- `Profile`
- `People & Permissions`
- `Projects`
- `API Keys`
- `Limits`
- `Audit Logs`
- `Integrations`
- `MCP Servers`

`Resource Policies` remains outside this surface as a separate advanced page.

## Scope Rules

- `Organization` is organization-scoped.
- `Profile` is personal-only.
- `People & Permissions` is organization-scoped.
- `Projects` is an organization-scoped project directory plus project detail management.
- `API Keys` supports organization-scoped and project-scoped keys in one surface.
- `Limits` supports organization defaults and project overrides.
- `Audit Logs` is organization-scoped with resource/user filtering.

## People & Permissions

`People & Permissions` contains these sub-tabs:
- `Members`
- `Invitations`
- `Groups`
- `Roles`

V1 group backing model:
- `Groups` reuse `org_units`.
- `org_units` are presented as governance groups inside settings, not as the primary app IA.

## Projects Surface

The `Projects` tab provides:
- searchable project table
- real project fields only
- project selection
- in-page detail panel

The project detail panel covers:
- name
- slug
- description
- status
- project members
- project API keys
- project limit overrides
- audit shortcut/filter seed

Columns such as geography, data retention, or spend do not ship unless backed by real data.

## Integrations Surface

`Integrations` keeps the existing credential management responsibilities:
- integration credential CRUD
- credential usage inspection
- credential status inspection
- force-disconnect delete flow

Current credential categories:
- `llm_provider`
- `vector_store`
- `tool_provider`
- `custom`

## Default Organization Settings

Organization defaults remain stored on the organization record (`Tenant.settings` in the current implementation):
- `default_chat_model_id`
- `default_embedding_model_id`
- `default_retrieval_policy`

Validation behavior:
- default chat model must resolve to an active chat model in organization/global scope
- default embedding model must resolve to an active embedding model in organization/global scope
- retrieval policy must be valid for the current enum

## Canonical API Surface

Settings governance APIs:
- `GET /api/settings/profile`
- `PATCH /api/settings/profile`
- `GET /api/settings/organization`
- `PATCH /api/settings/organization`
- `GET /api/settings/people/members`
- `GET /api/settings/people/invitations`
- `POST /api/settings/people/invitations`
- `DELETE /api/settings/people/invitations/{invite_id}`
- `GET /api/settings/people/groups`
- `POST /api/settings/people/groups`
- `PATCH /api/settings/people/groups/{group_id}`
- `DELETE /api/settings/people/groups/{group_id}`
- `GET /api/settings/people/roles`
- `POST /api/settings/people/roles`
- `PATCH /api/settings/people/roles/{role_id}`
- `DELETE /api/settings/people/roles/{role_id}`
- `POST /api/settings/people/role-assignments`
- `DELETE /api/settings/people/role-assignments/{assignment_id}`
- `GET /api/settings/projects`
- `GET /api/settings/projects/{project_slug}`
- `PATCH /api/settings/projects/{project_slug}`
- `GET /api/settings/projects/{project_slug}/members`
- `GET /api/settings/api-keys`
- `POST /api/settings/api-keys`
- `POST /api/settings/api-keys/{key_id}/revoke`
- `DELETE /api/settings/api-keys/{key_id}`
- `GET /api/settings/limits/organization`
- `PATCH /api/settings/limits/organization`
- `GET /api/settings/limits/projects/{project_slug}`
- `PATCH /api/settings/limits/projects/{project_slug}`
- `GET /api/settings/audit-logs`
- `GET /api/settings/audit-logs/count`
- `GET /api/settings/audit-logs/{log_id}`

Existing integrations APIs remain:
- `GET /admin/settings/credentials`
- `POST /admin/settings/credentials`
- `PATCH /admin/settings/credentials/{id}`
- `GET /admin/settings/credentials/{id}/usage`
- `DELETE /admin/settings/credentials/{id}`
- `GET /admin/settings/credentials/status`

## Behavioral Rules

- credential values are not returned directly; only key names are exposed in response payloads
- unsupported provider keys are rejected by category
- deleting a credential with linked resources is blocked unless `force_disconnect=true`
- force-disconnect deletion clears linked credential references on model bindings and knowledge stores
- force-disconnect deletion also removes tool `implementation.credentials_ref` links so runtime falls back to platform defaults
- new settings-facing APIs use organization/project semantics even if internal model names still retain `tenant`

## Runtime Resolution Rule

Credential resolution precedence:
1. explicit `credentials_ref`
2. organization default credential
3. platform environment default

## Canonical Implementation References

- `backend/app/api/routers/settings_governance.py`
- `backend/app/api/routers/settings.py`
- `backend/app/api/routers/org_units.py`
- `backend/app/services/project_api_key_service.py`
- `backend/app/services/tenant_api_key_service.py`
- `backend/app/services/credentials_service.py`
- `frontend-reshet/src/app/admin/settings/page.tsx`
- `frontend-reshet/src/app/admin/settings/components/GovernanceSections.tsx`
