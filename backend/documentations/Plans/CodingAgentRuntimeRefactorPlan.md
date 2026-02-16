# Coding Agent Runtime Refactor Plan (No Legacy Support)

Last Updated: 2026-02-16

## Summary
- Replace the current hardcoded ChatBuilder AI path with a real platform-runtime coding agent.
- Do not preserve old builder chat compatibility; remove legacy endpoints and code paths.
- Use platform execution primitives (`AgentExecutorService`, runtime adapters, tool runtime) as production truth.
- Use app-scoped run memory + durable checkpoints, with explicit run lifecycle APIs.

## Locked Decisions
- Execution truth: platform runtime, not SDK wrappers.
- API family: `/admin/apps/{app_id}/coding-agent/*`.
- Stream contract: new coding-agent SSE schema (not legacy builder schema).
- Run control: explicit lifecycle APIs (`create/list/get/stream/resume/cancel`).
- Apply mode: auto-apply + checkpoint for successful runs.
- Topology: single coding agent first.
- Memory: per-app run memory.
- Tool scope: built-in coding toolpack.
- Durability: include durable checkpointing now.
- Legacy handling: no support, no dual contracts, no compatibility adapters.

## New API Surface
- `POST /admin/apps/{app_id}/coding-agent/runs`
- `GET /admin/apps/{app_id}/coding-agent/runs`
- `GET /admin/apps/{app_id}/coding-agent/runs/{run_id}`
- `GET /admin/apps/{app_id}/coding-agent/runs/{run_id}/stream`
- `POST /admin/apps/{app_id}/coding-agent/runs/{run_id}/resume`
- `POST /admin/apps/{app_id}/coding-agent/runs/{run_id}/cancel`
- `GET /admin/apps/{app_id}/coding-agent/checkpoints`
- `POST /admin/apps/{app_id}/coding-agent/checkpoints/{checkpoint_id}/restore`

## New SSE Contract
Envelope:
- `{ event, run_id, app_id, seq, ts, stage, payload, diagnostics }`

Event types:
- `run.accepted`
- `plan.updated`
- `tool.started`
- `tool.completed`
- `tool.failed`
- `assistant.delta`
- `revision.created`
- `checkpoint.created`
- `run.completed`
- `run.failed`

## Canonical State and Persistence
- Canonical execution state: `AgentRun` and `AgentTrace`.
- Add app-builder linkage fields to `AgentRun`:
  - `surface`
  - `published_app_id`
  - `base_revision_id`
  - `result_revision_id`
  - `checkpoint_revision_id`
- Replace in-memory checkpoint saver for this path with durable checkpoint storage.
- Stop writing builder run truth into `PublishedAppBuilderConversationTurn`.

## Runtime and Tooling Architecture
- Run coding flows via platform runtime stack:
  - `AgentCompiler`
  - `LangGraphAdapter`
  - `AgentExecutorService`
- Seed one system coding-agent profile for builder usage.
- Register built-in coding toolpack through tool runtime:
  - file tools: `list_files`, `read_file`, `search_code`, `write_file`, `rename_file`, `delete_file`, `snapshot_files`
  - verification tools: `run_targeted_tests`, `build_worker_precheck`
  - checkpoint tools: create/restore checkpoint
- Enforce strict app-scoped sandbox policies and command allowlists.

## Legacy Removal (Intentional)
Remove old builder chat path and hardcoded loop modules:
- legacy chat stream route implementation under published apps admin builder chat flow
- `published_apps_admin_builder_agentic.py`
- `published_apps_admin_builder_model.py`
- `published_apps_admin_builder_patch.py`
- `published_apps_admin_builder_tools.py` (except reusable generic helpers, if extracted)

Remove old APIs:
- `/admin/apps/{app_id}/builder/chat/stream`
- `/admin/apps/{app_id}/builder/checkpoints`
- `/admin/apps/{app_id}/builder/undo`
- `/admin/apps/{app_id}/builder/revert-file`

Remove obsolete feature flags after cutover:
- `BUILDER_MODEL_PATCH_GENERATION_ENABLED`
- `BUILDER_AGENTIC_LOOP_ENABLED`
- `APPS_BUILDER_CHAT_SANDBOX_TOOLS_ENABLED`
- `APPS_BUILDER_CHAT_COMMANDS_ENABLED`
- `APPS_BUILDER_CHAT_WORKER_PRECHECK_ENABLED`

## Phased Delivery
1. Phase 0: Docs + tracker bootstrap.
2. Phase 1: Durable checkpointer + `AgentRun` schema updates.
3. Phase 2: Built-in coding toolpack + policy.
4. Phase 3: New `/coding-agent/*` backend APIs + stream mapping.
5. Phase 4: Revision/checkpoint integration (auto-apply + restore).
6. Phase 5: Frontend migration to new contract.
7. Phase 6: Legacy code and endpoint deletion.
8. Phase 7: Stabilization + cleanup migrations.

## Test Plan
Backend feature directories:
- `backend/tests/coding_agent_api/`
- `backend/tests/coding_agent_runtime/`
- `backend/tests/coding_agent_tools/`
- `backend/tests/coding_agent_checkpoints/`

Frontend feature directory:
- `frontend-reshet/src/__tests__/coding_agent_workspace/`

Required scenarios:
- Run lifecycle (`create/list/get/stream/resume/cancel`)
- Tool lifecycle event correctness
- Auto-apply + checkpoint creation
- Checkpoint restore correctness
- Durable resume after restart
- Policy denials and command allowlist enforcement
- Worker precheck and targeted test failure handling

Acceptance criteria:
- All app-builder AI coding actions route through `/coding-agent/*`.
- No references to removed legacy builder chat endpoints remain.
- Durable run resume works reliably.
- Legacy hardcoded builder chat modules are deleted.

## Rollout and Tracking
- Implement in phases but with no compatibility layer.
- Track each phase in a dedicated implementation tracker doc in `backend/documentations/Plans/`.
- Update tracker after each phase with:
  - exact commands run
  - pass/fail results
  - known gaps

## Assumptions
- There are no production users relying on the old builder chat contract.
- Breaking changes are acceptable in this development stage.
- Single-agent architecture is sufficient for the first production-grade coding-agent release.
