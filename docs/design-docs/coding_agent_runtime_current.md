# Coding Agent Runtime Current

Last Updated: 2026-03-12

This document is the canonical current-state overview for the published-app coding-agent runtime.

## Current Model

- The execution engine is hard-cut to OpenCode.
- Backend acts as a product adapter for auth, sandbox binding, chat history, revision materialization, and run-state reconciliation.
- Live run state converges from OpenCode session status plus assistant finish semantics rather than from an older replay/event-log orchestrator.
- Prompt queueing is frontend-owned; the backend no longer acts as a durable prompt queue manager.

## Backend Entry Points

- API surface:
  - `backend/app/api/routers/published_apps_admin_routes_coding_agent_v2.py`
- Runtime/service layer:
  - `backend/app/services/published_app_coding_agent_runtime.py`
  - `backend/app/services/published_app_coding_agent_runtime_streaming.py`
  - `backend/app/services/published_app_coding_agent_runtime_sandbox.py`
  - `backend/app/services/published_app_coding_run_monitor.py`
  - `backend/app/services/published_app_coding_chat_history_service.py`
- Engine/client layer:
  - `backend/app/services/published_app_coding_agent_engines/opencode_engine.py`
  - `backend/app/services/opencode_server_client.py`

## Verified Current Contract

- Endpoints live under `/admin/apps/{app_id}/coding-agent/v2/*`.
- Implemented routes include prompts, run lookup, run stream, cancel, answer-question, chat-session list/detail, active-run, checkpoints, and checkpoint restore.
- Auto-model resolution still defaults to `opencode/big-pickle`.
- Run tool events are persisted on `run.output_result.tool_events` and returned through chat-session detail responses.
- Non-terminal stream closure is handled reconcile-first; aggressive fail-close behavior remains env-gated.
- Question/approval flow is part of the active API contract through `answer-question`.

## Operational Behavior

- Coding-agent runs execute against the canonical shared Apps Builder workspace.
- Completion may wait for the next successful preview build before result revisions are materialized.
- Publish/build failures can trigger a best-effort auto-fix prompt against an existing coding-agent chat session.
- Tool event passthrough defaults to raw OpenCode semantics, with optional normalization for legacy UI paths.

## Canonical Related Docs

- `docs/design-docs/apps_builder_current.md`
- `docs/design-docs/agent_execution_current.md`
- `docs/product-specs/published_apps_spec.md`

## Legacy Detail

The previous detailed runtime note now lives at `backend/documentations/summary/CustomCodingAgent.md` as a legacy pointer.
