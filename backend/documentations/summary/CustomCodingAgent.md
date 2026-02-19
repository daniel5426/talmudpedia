# Custom Coding Agent

Last Updated: 2026-02-18

## Source Documents Consolidated
- Note: the historical plan files listed in this section were archived/removed from
  `backend/documentations/Plans/`; this summary remains as the retained consolidated record.
- `backend/documentations/Plans/ChatBuilderProductionRoadmap.md`
- `backend/documentations/Plans/ChatBuilderProductionCompletionImplementationTracker.md`
- `backend/documentations/Plans/CodingAgentRuntimeRefactorPlan.md`
- `backend/documentations/Plans/CodingAgentRuntimeRefactorImplementationTracker.md`
- `backend/documentations/Plans/CodingAgentHardeningAndPerRunModelSelectionPlan.md`

## 1) ChatBuilderProductionRoadmap.md (Summary)
- Defined the original parity target: move Builder Chat from demo-like patching into a production coding assistant.
- Established migration to backend-built Vite/static runtime as source of truth.
- Set quality bars: reliable multi-turn coding loop, tool-augmented repairs, safer patch policy, build/validation gating, and better observability.
- Identified key gaps at that stage: intelligence quality, migration completeness, review UX, and operational metrics/evals.

## 2) ChatBuilderProductionCompletionImplementationTracker.md (Summary)
- Recorded the completion of the ChatBuilder production-completion phases (checkpoints, undo/revert APIs, evented stream UX, tests).
- Later marked itself as historical/superseded after coding-agent cutover.
- Noted post-cutover hardening items (revision-conflict retry, broader file path policy, regression tests).
- Main takeaway: ChatBuilder track was completed for its era, then replaced by coding-agent contracts.

## 3) CodingAgentRuntimeRefactorPlan.md (Summary)
- Declared hard cutover from legacy ChatBuilder runtime to platform runtime primitives.
- Locked the new API family: `/admin/apps/{app_id}/coding-agent/*`.
- Defined new SSE event envelope and run lifecycle model.
- Required durable checkpoints, app/run linkage fields, and tool-runtime based coding toolpack.
- Explicitly removed legacy builder chat endpoints/modules and old feature-flag paths.

## 4) CodingAgentRuntimeRefactorImplementationTracker.md (Summary)
- Tracks implementation status of that cutover and subsequent hardening.
- Reports completed phases for core refactor (API/runtime/frontend migration + legacy deletion), with stabilization continuing.
- Documents major delivered capabilities:
  - run-level model selection/pinning (`requested_model_id`, `resolved_model_id`),
  - strict tool input validation and normalized failure envelopes,
  - patch-first runtime improvements,
  - SSE framing and streaming reliability fixes,
  - UI contract migration to coding-agent stream semantics,
  - optional OpenCode engine path under same external API contract.
- Captures test command history and outcomes for backend/frontend suites.

## 5) CodingAgentHardeningAndPerRunModelSelectionPlan.md (Summary)
- Split hardening into two phases.
- Phase 1 (must-ship) focused on correctness and per-run model UX:
  - API support for `model_id`,
  - fail-fast model-unavailable contract,
  - run-pinned model execution,
  - coding-agent tool required-field validation.
- Phase 2 listed remaining depth work: runtime/event assertions, cancellation/output hardening, multi-instance durability, and visual E2E.
- Status in the doc marks Phase 1 finished; deeper Phase 2 work remains follow-up.

## Consolidated Current State (AI + OpenCode)
- Current production contract is coding-agent run lifecycle + SSE events + checkpoint restore.
- Legacy ChatBuilder chat contracts are intentionally retired.
- Per-run model selection is first-class (`Auto` or explicit model) and execution is pinned to resolved model at run time.
- OpenCode is integrated as an optional engine behind the same coding-agent API, with fail-closed behavior and deterministic error contracts.

## Latest OpenCode Updates (2026-02-19)
- Official OpenCode mode now streams from `/global/event` in real time (with snapshot polling fallback), so assistant output is emitted incrementally instead of waiting for block-style completion.
- Tool timeline translation was hardened so early tool parts are no longer dropped before assistant-role metadata arrives; `tool.started` / `tool.completed` / `tool.failed` now surface more reliably (not only occasional `glob`).
- Incremental text handling now tracks part offsets and filters reasoning/thought parts from user-visible assistant deltas, preventing noisy or duplicated text.
- Terminal/error handling was tightened:
  - keep fail-closed behavior for true assistant/session failures,
  - avoid false terminal failures from recoverable intermediate tool-step errors when a later assistant turn succeeds.
- Official run start path prefers `POST /session/{id}/prompt_async` to avoid blocking and allow stream attachment earlier; fallback to legacy `POST /session/{id}/message` remains.
- Live integration/test coverage was expanded:
  - added unit tests for global-event streaming + tool events + reasoning suppression,
  - retained and improved live roundtrip and live filesystem-edit tests.

## OpenCode Validation Snapshot
- `cd backend && PYTHONPATH=. pytest tests/opencode_server_client -q` -> pass (`19 passed, 2 skipped`).
- `cd backend && OPENCODE_LIVE_TEST=1 OPENCODE_LIVE_FULL_TASK=1 APPS_CODING_AGENT_OPENCODE_BASE_URL=http://127.0.0.1:8788 OPENCODE_LIVE_MODEL_ID=opencode/gpt-5-nano PYTHONPATH=. pytest tests/opencode_server_client/test_opencode_server_client_live.py -q` -> pass (`2 passed`).
- `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q` -> pass (`19 passed`).

## Decision Record Preserved by This Merge
- Keep platform runtime primitives as source of truth.
- Keep coding-agent API/SSE contract as the stable external interface.
- Keep run-scoped model pinning and tool validation semantics.
- Keep OpenCode as optional, env-gated, fail-closed secondary engine.
