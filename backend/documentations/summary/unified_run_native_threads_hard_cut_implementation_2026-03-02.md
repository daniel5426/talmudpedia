# Unified Run-Native Threads Hard Cut Implementation

Last Updated: 2026-03-02

## Scope
Implemented the hard-cut thread contract for non-coding execution surfaces:
- `chat_id` -> `thread_id` for unified run requests.
- `X-Chat-ID` -> `X-Thread-ID` stream response header.
- Admin history APIs migrated from `/admin/chats*` to `/admin/threads*`.
- Host runtime history APIs added under `/_talmudpedia/threads*`.
- Runtime SDK contract bumped to thread request contract and thread response metadata.

## Backend Changes
- Added/used run-native thread persistence:
  - `agent_threads`, `agent_thread_turns`, `agent_runs.thread_id` (migration + models + service).
  - `AgentExecutorService.start_run` resolves/creates threads and persists `thread_id` on runs.
  - `AgentExecutorService.run_and_stream` starts/completes thread turns and persists usage/status.
- Unified request schema:
  - `ExecuteAgentRequest` now includes `thread_id`.
  - Published runtime stream payload now uses `thread_id`.
- Stream metadata:
  - `/agents/{agent_id}/stream` now emits `X-Thread-ID` and includes `thread_id` in accepted payload.
  - Published runtime stream adapters include `thread_id` and emit `X-Thread-ID`.
- Runtime bootstrap:
  - Added `request_contract_version: "thread.v1"` to bootstrap response model.
- Admin API hard rename:
  - `POST /admin/threads/bulk-delete`
  - `GET /admin/threads`
  - `GET /admin/threads/{thread_id}`
  - `GET /admin/users/{user_id}/threads`
  - User stats now expose `threads_count`.
- Host runtime history:
  - `GET /_talmudpedia/threads`
  - `GET /_talmudpedia/threads/{thread_id}`
- CORS exposed headers updated to `X-Thread-ID`.

## Frontend + SDK Changes
- Runtime SDK (`@talmudpedia/runtime-sdk`):
  - Major version bump to `1.0.0`.
  - `RuntimeInput.chat_id` -> `RuntimeInput.thread_id`.
  - `RuntimeStreamResult.chatId` -> `RuntimeStreamResult.threadId`.
  - Enforces bootstrap `request_contract_version === "thread.v1"`.
  - Reads `X-Thread-ID` header.
- Admin frontend:
  - Routes moved to `/admin/threads` and `/admin/users/{userId}/threads`.
  - New thread table component and thread detail pages.
  - Admin service now calls `/admin/threads*` endpoints.
  - User details consume `stats.threads_count`.
- Published app templates:
  - Template runtime SDK and app code switched to `thread_id` + `X-Thread-ID` usage.

## Notes
- Legacy voice/chat surfaces and coding-agent v2 chat/session naming were intentionally left out of this hard-cut scope.
- Path-mode published runtime endpoints remain removed (410), while host runtime history now uses `/_talmudpedia/threads*`.
