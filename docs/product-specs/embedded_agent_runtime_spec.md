# Embedded Agent Runtime Spec

Last Updated: 2026-03-16

This document defines the canonical v1 external embed/plugin contract for published agents used inside customer-owned applications.

## Product Boundary

Embedded agent runtime is a separate product from published apps.

- Published apps are app-scoped products with app auth, app sessions, app delivery, builder flows, and optional platform-hosted frontend runtime.
- Embedded agent runtime is an agent-scoped server integration surface for customers that already have their own application and only want to call a published agent.
- Embedded agent runtime does not require creating a published app.

Important boundary:
- `/agents/{id}/stream` remains the internal/control-plane execution route for authenticated platform users and workload principals.
- `/public/embed/agents/{agent_id}/*` is the external embed contract.

## V1 Scope

V1 is server-side only.

- Customer backend calls the platform directly.
- Customer backend authenticates with a tenant API key held as a secret.
- Customer frontend does not call the platform directly in the supported v1 model.
- No bootstrap endpoint is required in v1.

## Authentication Model

V1 authentication uses tenant API keys.

- Tenant API keys are created and managed under `/admin/security/api-keys`.
- Keys are tenant-scoped, named, revocable, and hashed at rest.
- Only keys with `agents.embed` can access the embed runtime in this phase.
- Embed requests authenticate with `Authorization: Bearer <tenant_api_key>`.

Admin API-key routes:
- `POST /admin/security/api-keys`
- `GET /admin/security/api-keys`
- `POST /admin/security/api-keys/{key_id}/revoke`

## Eligible Agents

- Only published agents are eligible for embed runtime access.
- Draft agents are rejected.
- Embed access is tenant-scoped through the tenant API key.

## Runtime Surface

The canonical public embed routes are:

- `POST /public/embed/agents/{agent_id}/chat/stream`
- `GET /public/embed/agents/{agent_id}/threads`
- `GET /public/embed/agents/{agent_id}/threads/{thread_id}`

## Request Contract

`POST /public/embed/agents/{agent_id}/chat/stream`

Required:
- `external_user_id`

Optional:
- `input`
- `messages`
- `thread_id`
- `external_session_id`
- `metadata`
- `client`

Notes:
- `thread_id` resumes an existing embedded-runtime thread when it belongs to the same tenant, agent, and `external_user_id`.
- `external_session_id` is optional partitioning metadata, not the primary ownership key.

## Thread Ownership

Embedded runtime conversation history is platform-managed.

Ownership is enforced by:
- tenant
- agent
- `external_user_id`

Persisted thread records also store:
- `external_session_id`
- `tenant_api_key_id`
- embedded runtime thread surface marker

History rules:
- `external_user_id` is required on all embed runtime and history calls
- thread list/detail calls are always agent-scoped
- cross-user and cross-agent thread access is rejected

## Stream Contract

Embedded agent runtime reuses the shared execution core and the current public-safe SSE contract.

- stream version: `run-stream.v2`
- thread request semantics: `thread.v1`
- `X-Thread-ID` is returned on stream responses

The embed surface reuses:
- `AgentExecutorService`
- shared thread service
- shared stream filtering
- shared `run-stream.v2` normalization

It does not reuse the published-app route/auth/session model.

## SDK Surface

The supported SDK direction for v1 is server-side:

- Python control SDK: `embedded_agents.stream_agent`, `list_agent_threads`, `get_agent_thread`
- TypeScript server helper: embedded-agent client methods with the same shape

No browser runtime SDK integration is required in this phase.

## Canonical Implementation References

- `backend/app/api/routers/embedded_agents_public.py`
- `backend/app/api/routers/tenant_api_keys.py`
- `backend/app/services/embedded_agent_runtime_service.py`
- `backend/app/services/tenant_api_key_service.py`
- `backend/app/services/thread_service.py`
- `backend/app/agent/execution/service.py`
- `backend/app/db/postgres/models/security.py`
- `backend/app/db/postgres/models/agent_threads.py`
