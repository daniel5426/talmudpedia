# Organization And Project Workflow Spec

Last Updated: 2026-04-19

This document is the canonical product/specification reference for the browser sign-in flow, active organization/project context, and the organization/project admin workflow.

## Canonical Domain Model

The primary control-plane model is:

- user
- organization
- project

Organizations are the top-level identity, membership, invite, and governance boundary.

Projects are the primary runtime and day-to-day product boundary for:

- agents
- apps
- tools
- prompts
- artifacts
- MCP connections
- knowledge and RAG resources
- project-scoped credentials and API keys
- runtime usage and quotas

`org_units` remain optional internal organization structure only. They are not the primary browser auth or runtime context.

## Browser Auth Model

Browser auth uses WorkOS AuthKit plus secure HTTP-only cookies.

The browser auth context carries:

- authenticated user identity from WorkOS
- active organization identity from WorkOS
- active project id from a local project cookie

The browser control plane must resolve identity and active context from the server session, not from:

- browser-local bearer tokens
- JWT-embedded tenant context
- first-membership inference
- `X-Tenant-ID` headers as the source of truth

Programmatic auth remains separate:

- browser flows use the WorkOS sealed session cookie plus the local project cookie
- API/service flows may use bearer tokens or project-scoped machine credentials where explicitly designed

## Default Signup Workflow

The canonical signup flow is:

1. user starts the hosted sign-up flow
2. WorkOS authenticates the user and redirects back to the callback
3. backend maps the WorkOS user into a local user
4. if no organization exists yet, system creates a new organization for that user
5. system creates a default project inside that organization
6. system assigns the user as organization owner and default-project owner locally
7. backend stores the WorkOS sealed session cookie and local project cookie
8. user lands inside the default project

Current implemented endpoints:

- `GET|POST /auth/signup`
- `GET|POST /auth/register`
- `GET /auth/callback`

## Sign-In Workflow

The canonical sign-in flow is:

1. user starts from the platform sign-in or sign-up page
2. backend redirects the browser into hosted WorkOS AuthKit
3. WorkOS redirects back to `GET /auth/callback`
4. backend stores a sealed WorkOS session cookie and resolves the active organization
5. backend resolves the active local project for that organization and stores the local project cookie
6. frontend hydrates the auth/session store from `GET /auth/session`

Current implemented endpoints:

- `GET|POST /auth/login`
- `GET|POST /auth/signup`
- `GET /auth/callback`
- `GET /auth/session`
- `POST /auth/logout`

Current implementation detail:

- WorkOS is the source of truth for browser user identity and active organization
- the active project remains local and is resolved after the WorkOS session is established
- once the session exists, later control-plane requests should use the active WorkOS org context plus the local project cookie rather than re-deriving both from memberships

## Active Context Workflow

Active context switching is session-based.

Canonical behavior:

- top-level organization switcher changes the active organization in session
- project switcher changes the active project inside the active organization
- permissions and visible resources update immediately after the session switch

Current implemented endpoints:

- `POST /auth/context/organization`
- `POST /auth/context/project`

Current frontend behavior:

- session payload hydrates user summary, active organization, active project, accessible organizations, accessible projects, and effective scopes

## Invite Workflow

Canonical invite behavior:

1. organization admin creates an invite for an email address
2. invite may include initial project assignments
3. invite token is time-bound
4. accepting the invite requires an authenticated WorkOS user for the invited email
5. accepted user is attached to the organization
6. accepted user receives the requested project access
7. the active local project cookie is updated for the accepted organization

Current implemented organization APIs:

- `GET /api/organizations`
- `POST /api/organizations`
- `GET /api/organizations/{organization_slug}`
- `PATCH /api/organizations/{organization_slug}`
- `GET /api/organizations/{organization_slug}/projects`
- `POST /api/organizations/{organization_slug}/projects`
- `PATCH /api/organizations/{organization_slug}/projects/{project_slug}`
- `GET /api/organizations/{organization_slug}/members`
- `GET /api/organizations/{organization_slug}/invites`
- `POST /api/organizations/{organization_slug}/invites`
- `POST /api/organizations/invites/accept`

## Authorization Model

Authorization is scope-driven.

There are two primary scope layers:

- organization scopes
- project scopes

Organization scopes cover concerns such as:

- organization membership and invites
- organization settings
- organization-wide security and governance
- cross-project administration

Project scopes cover concerns such as:

- project-owned runtime resources
- agent/app/tool/prompt/artifact operations
- project-specific operational and runtime actions

Role strings alone should not be treated as the long-term frontend authorization model.

## Admin Surface Information Architecture

The intended browser control-plane grouping is:

- Organization
- Projects
- Members & Invites
- Security & Roles
- Organization Settings
- Project Settings

`/admin/settings` should remain a focused settings hub, not a catch-all replacement for organization and security administration.

## Default System Profiles

Default system profiles are expected to materialize from lifecycle/bootstrap flows, not from startup scans.

Current canonical profiles are:

- `platform-architect`
- `artifact-coding-agent`
- `published-app-coding-agent`

Current intended bootstrap shape:

- organization bootstrap ensures `platform-architect`
- project bootstrap ensures coding-agent system profiles

## Current Known Cleanup Boundary

The control-plane architecture has moved to organization/project/session semantics, but some route names and stored fields in the broader system still retain `tenant` terminology.

Those remaining names are implementation debt, not the intended product model.
