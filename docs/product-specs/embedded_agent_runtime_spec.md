# Embedded Agent Runtime Spec

Last Updated: 2026-03-19

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
- `POST /public/embed/agents/{agent_id}/attachments/upload`
- `GET /public/embed/agents/{agent_id}/threads`
- `GET /public/embed/agents/{agent_id}/threads/{thread_id}`
- `DELETE /public/embed/agents/{agent_id}/threads/{thread_id}`

V1 does not include:

- any separate public embed route for historical run-event fetch beyond thread detail
- any public embed route for agent/tool/admin resource mutation

## Request Contract

`POST /public/embed/agents/{agent_id}/chat/stream`

Required:
- `external_user_id`

Optional:
- `input`
- `messages`
- `attachment_ids`
- `thread_id`
- `external_session_id`
- `metadata`
- `client`

Notes:
- Attachments are upload-first. Chat requests only reference uploaded `attachment_ids`.
- `thread_id` resumes an existing embedded-runtime thread when it belongs to the same tenant, agent, and `external_user_id`.
- `external_session_id` is optional partitioning metadata, not the primary ownership key.

`POST /public/embed/agents/{agent_id}/attachments/upload`

Required:
- multipart `files`
- `external_user_id`

Optional:
- `external_session_id`
- `thread_id`

Behavior:
- uploads are tenant-scoped and agent-scoped
- attachments can be reused within the same thread
- supported v1 kinds are `image`, `document`, and `audio`

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
- TypeScript package: `@agents24/embed-sdk`

No browser runtime SDK integration is required in this phase.

`@agents24/embed-sdk` is the canonical TypeScript integration surface for the embed runtime:

- Node-only in v1
- distributed as a public npm package
- wraps the existing `/public/embed/agents/{agent_id}/*` routes exactly
- does not provide browser auth helpers, bootstrap flows, cookies, localStorage integration, or published-app account/session models

Customer architecture must remain:

- customer frontend
- customer backend
- `@agents24/embed-sdk`
- Talmudpedia embed API
- published agent

The customer frontend must never hold the tenant API key.

## Exact V1 SDK Methods

The current TypeScript SDK maps 1:1 to the public embed routes:

- `streamAgent(agentId, payload, onEvent?)` -> `POST /public/embed/agents/{agent_id}/chat/stream`
- `uploadAgentAttachments(agentId, options)` -> `POST /public/embed/agents/{agent_id}/attachments/upload`
- `listAgentThreads(agentId, options)` -> `GET /public/embed/agents/{agent_id}/threads`
- `getAgentThread(agentId, threadId, options)` -> `GET /public/embed/agents/{agent_id}/threads/{thread_id}`
- `deleteAgentThread(agentId, threadId, options)` -> `DELETE /public/embed/agents/{agent_id}/threads/{thread_id}`

The SDK does not currently expose:

- fetch historical event streams for a completed run
- browser auth/bootstrap helpers
- retry, timeout, or abort controls
- control-plane/admin operations

## Thread Detail Contract Boundary

`GET /public/embed/agents/{agent_id}/threads/{thread_id}` returns thread summary plus persisted turns.

Each turn includes:

- `id`
- `run_id`
- `turn_index`
- `user_input_text`
- `assistant_output_text`
- `status`
- `usage_tokens`
- `metadata`
- `attachments`
- `created_at`
- `completed_at`
- `run_events`

Important boundary:

- `run_id` is exposed on turns
- `run_events` provides ordered historical non-text public run events for that turn
- these events are returned in `run-stream.v2` envelope shape
- this is intended for replaying tool/reasoning history on old chats without bypassing the embed contract
- final assistant text still comes from `assistant_output_text`, not token replay

## Canonical Implementation References

- `backend/app/api/routers/embedded_agents_public.py`
- `backend/app/api/routers/tenant_api_keys.py`
- `backend/app/services/embedded_agent_runtime_service.py`
- `backend/app/services/tenant_api_key_service.py`
- `backend/app/services/thread_service.py`
- `backend/app/agent/execution/service.py`
- `backend/app/db/postgres/models/security.py`
- `backend/app/db/postgres/models/agent_threads.py`
- `packages/embed-sdk/`
- `docs/references/embedded_agent_sdk_standalone_integration_guide.md`
