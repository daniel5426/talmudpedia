# Coding Agent Runtime Refactor Implementation Tracker

Last Updated: 2026-02-16

## Scope
Implements first-pass backend cutover from legacy builder chat runtime to `/admin/apps/{app_id}/coding-agent/*` APIs using platform runtime primitives.

## Phase Status
- Phase 1 (durability + run metadata): completed
- Phase 2 (coding toolpack + policy): completed
- Phase 3 (coding-agent backend APIs + stream mapping): completed
- Phase 4 (auto-apply revision + checkpoint restore): completed
- Phase 5 (frontend contract migration): completed
- Phase 6 (legacy endpoint/module deletion): completed
- Phase 7 (stabilization + backend test migration): in progress
- Remaining: broader runtime hardening, expanded coding-agent tool/runtime assertions, deeper frontend event assertions

## Implemented Changes
- Added durable LangGraph checkpointer: `backend/app/agent/execution/durable_checkpointer.py`
- Switched `AgentExecutorService` to durable checkpointer.
- Extended `AgentRun` linkage fields for coding-agent app/revision context.
- Added Alembic migration:
  - `backend/alembic/versions/5d7e9b1c2a3f_add_coding_agent_linkage_fields_to_agent_runs.py`
- Added coding-agent tooling/profile/runtime services:
  - `backend/app/services/published_app_coding_agent_tools.py`
  - `backend/app/services/published_app_coding_agent_profile.py`
  - `backend/app/services/published_app_coding_agent_runtime.py`
- Added new coding-agent routes:
  - `backend/app/api/routers/published_apps_admin_routes_coding_agent.py`
- Removed legacy modules/endpoints:
  - deleted `published_apps_admin_routes_chat.py`
  - deleted `published_apps_admin_builder_agentic.py`
  - deleted `published_apps_admin_builder_model.py`
  - deleted `published_apps_admin_builder_patch.py`
  - removed routes `/builder/chat/stream`, `/builder/checkpoints`, `/builder/undo`, `/builder/revert-file`
- Removed obsolete backend feature flag code paths for legacy builder chat toggles.
- Migrated backend test coverage away from removed legacy builder chat APIs:
  - trimmed `backend/tests/published_apps/test_builder_revisions.py` to non-legacy builder revision flows
  - added `backend/tests/coding_agent_api/test_run_lifecycle.py`
  - added `backend/tests/coding_agent_checkpoints/test_checkpoint_restore.py`
  - updated `backend/tests/published_apps/test_admin_apps_publish_rules.py` to assert environment-derived publish URLs
  - added feature `test_state.md` files:
    - `backend/tests/coding_agent_api/test_state.md`
    - `backend/tests/coding_agent_checkpoints/test_state.md`
- Migrated frontend builder workspace contract to coding-agent APIs:
  - replaced legacy `/builder/chat/stream` call with `/coding-agent/runs` + `/coding-agent/runs/{run_id}/stream`
  - replaced undo flow (`/builder/undo`) with checkpoint restore (`/coding-agent/checkpoints` + `/restore`)
  - updated frontend SSE handling to coding-agent event envelope (`run.accepted`, `assistant.delta`, `tool.*`, `revision.created`, `checkpoint.created`, `run.completed`, `run.failed`)
  - removed frontend source references to deleted legacy builder chat/checkpoint/undo/revert endpoints

## Commands Run
1. `python3 -m compileall backend/app backend/alembic/versions/5d7e9b1c2a3f_add_coding_agent_linkage_fields_to_agent_runs.py`
- Result: pass

2. `PYTHONPATH=backend python3 - <<'PY' ...` (router import + route presence check)
- Result: pass
- Confirmed: `/admin/apps/{app_id}/coding-agent/*` routes registered
- Confirmed: legacy `/admin/apps/{app_id}/builder/chat/stream` and removed builder mutation routes are not registered

3. `PYTHONPATH=backend pytest -q backend/tests/published_apps/test_builder_revisions.py`
- Result: pass (7 passed)

4. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_api`
- Result: pass (4 passed)

5. `PYTHONPATH=backend pytest -q backend/tests/coding_agent_checkpoints`
- Result: pass (2 passed)

6. `PYTHONPATH=backend pytest -q backend/tests/published_apps`
- Result: pass (31 passed)

7. `cd frontend-reshet && npm test -- src/__tests__/published_apps/apps_builder_workspace.test.tsx --runInBand`
- Result: pass (1 suite, 16 tests)

8. `cd frontend-reshet && npm test -- src/__tests__/published_apps --runInBand`
- Result: pass (5 suites, 21 tests)

## Known Gaps
- Coding-agent stream tests currently validate generator execution/headers in API tests; deeper deterministic envelope assertions should be added in runtime-focused tests.
- Frontend workspace tests validate coding-agent run creation/stream usage and checkpoint restore flow, but can still add richer assertions for tool payload semantics and failure envelopes.
- Tool output semantics are functional but still need production-level tightening for richer diagnostics and cancellation propagation.
- Durable checkpointer is file-backed in this pass; a database-backed saver can be added later for stronger multi-instance durability.
