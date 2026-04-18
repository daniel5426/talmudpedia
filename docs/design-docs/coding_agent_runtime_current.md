# Coding Agent Runtime Current

Last Updated: 2026-04-18

This document is the canonical current-state overview for the published-app coding-agent runtime.

## Current Model

- The execution engine is hard-cut to OpenCode.
- Backend acts as a product adapter for auth, sandbox binding, chat-session persistence, revision materialization, and official OpenCode session/event translation.
- Apps-builder coding chat is now session-native: one `PublishedAppCodingChatSession` maps to one OpenCode `session`.
- User turns are submitted through the official async session contract, and live updates come from one session-scoped SSE subscription.
- Prompt queueing remains frontend-owned; the backend no longer acts as a durable prompt queue manager.
- For the active open chat session, the frontend timeline is stream-owned during live conversation; history hydration is used for initial load, reopen, and older-message pagination, not as the primary live reconciliation path after every idle.

## Backend Entry Points

- API surface:
  - `backend/app/api/routers/published_apps_admin_routes_coding_agent_v2.py`
- Runtime/service layer:
  - `backend/app/services/published_app_coding_chat_session_service.py`
  - `backend/app/services/published_app_coding_chat_history_service.py`
- Engine/client layer:
  - `backend/app/services/published_app_coding_agent_engines/opencode_engine.py`
  - `backend/app/services/opencode_server_client.py`

## Verified Current Contract

- Endpoints live under `/admin/apps/{app_id}/coding-agent/v2/*`.
- Implemented routes are session-native:
  - `POST /chat-sessions`
  - `GET /chat-sessions`
  - `GET /chat-sessions/{session_id}`
  - `GET /chat-sessions/{session_id}/messages`
  - `POST /chat-sessions/{session_id}/messages`
  - `GET /chat-sessions/{session_id}/events`
  - `POST /chat-sessions/{session_id}/abort`
  - `POST /chat-sessions/{session_id}/permissions/{permission_id}`
- Legacy run-shaped v2 routes such as `/prompts`, `/runs/{run_id}/*`, queue endpoints, and active-run lookup are removed from the current contract.
- Auto-model resolution still defaults to `opencode/big-pickle`.
- Chat history is hydrated from official OpenCode session messages, and assistant/tool updates are keyed by official message/part ids.
- SSE completion is driven by official session/message events, not by transport EOF heuristics or post-idle history overwrite.
- Permission/approval flow is part of the active API contract through the session permission route.

## Operational Behavior

- Coding-agent chat sessions execute against the canonical shared Apps Builder workspace.
- Completion may wait for the next successful preview build before result revisions are materialized.
- Publish/build failures can trigger a best-effort auto-fix prompt against an existing coding-agent chat session.
- Tool event passthrough stays close to raw OpenCode semantics, with only thin session-scoped normalization for the product UI.

## Canonical Related Docs

- `docs/design-docs/apps_builder_current.md`
- `docs/design-docs/agent_execution_current.md`
- `docs/product-specs/published_apps_spec.md`

## Legacy Detail

The previous detailed runtime note now lives at `backend/documentations/summary/CustomCodingAgent.md` as a legacy pointer.
