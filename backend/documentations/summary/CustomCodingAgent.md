# Custom Coding Agent

Last Updated: 2026-02-21

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
  - OpenCode-first engine path under the same external API contract, with native fallback policy controls.
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
- OpenCode is now the default coding-agent engine; native execution is opt-in via backend/frontend env policy.
- Chat memory continuity is now server-persisted per `(published_app_id, user_id)` chat session and reused across runs.

## Latest OpenCode-First + Durable Chat History Updates (2026-02-19)
- `POST /admin/apps/{app_id}/coding-agent/runs` now accepts optional `chat_session_id`; request `engine` is optional and resolves from backend policy.
- Engine policy is backend-authoritative:
  - default: `APPS_CODING_AGENT_DEFAULT_ENGINE=opencode`,
  - native allowed only when `APPS_CODING_AGENT_NATIVE_ENABLED=1`,
  - explicit native requests return deterministic `400` `CODING_AGENT_ENGINE_UNAVAILABLE` when disabled.
- New chat history APIs are available:
  - `GET /admin/apps/{app_id}/coding-agent/chat-sessions`
  - `GET /admin/apps/{app_id}/coding-agent/chat-sessions/{session_id}`
- New persisted storage tables:
  - `published_app_coding_chat_sessions`
  - `published_app_coding_chat_messages`
- Run creation now builds effective history from persisted turns (session-scoped), persists user messages immediately, and persists assistant messages on terminal stream events.
- OpenCode prompt construction now includes bounded prior user/assistant turns via a dedicated prompt-history formatter so context continuity works across fresh OpenCode session bootstraps.
- Frontend builder chat no longer exposes an engine dropdown; engine is resolved from `NEXT_PUBLIC_APPS_CODING_AGENT_ENGINE` (default `opencode`).

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

## Latest Sandbox + Draft Sync Updates (2026-02-19)
- OpenCode sandbox mode now runs against sandbox-controller-scoped sessions and supports per-sandbox OpenCode process routing in the local dev shim, aligning OpenCode workspace root with the active draft sandbox.
- Coding run creation now refreshes from active builder sandbox state before execution, reducing stale template-base runs.
- Snapshot-to-draft persistence now sanitizes generated artifacts so build outputs are not saved as source files.
  - Filtered examples: `dist/`, `.vite/`, `.turbo/`, `.cache/`, `.parcel-cache/`, `.npm/`, `.pnpm-store/`, `.yarn/`, `*.tsbuildinfo`, `.eslintcache`, `.stylelintcache`.
- Builder blocked path policy was expanded to include these generated directories, reducing accidental artifact persistence and draft file-count inflation.
- OpenCode completion semantics now support recovered edit flows after patch mismatches:
  - default remains fail-closed when `apply_patch` failures are not followed by a successful follow-up edit,
  - `apply_patch` success detection is tolerant to broader successful completion payload shapes (not only `ok + applied_files`),
  - strict fail-closed behavior is policy-tunable with `APPS_CODING_AGENT_OPENCODE_FAIL_ON_UNRECOVERED_APPLY_PATCH` (default `1`).
- OpenCode patch auto-verification defaults on for OpenCode runs and can fail the tool result when verification commands fail.
- Draft-dev controller SSE stream handling is hardened by default (read timeout disabled unless explicitly configured), reducing mid-run stream disconnects.
- Current known behavior: assistant identity text can still reflect underlying OpenCode persona unless explicitly overridden by upstream prompt/response policy.

## Latest Selected-Agent Integration Contract Updates (2026-02-19)
- Added builder endpoint:
  - `GET /admin/apps/{app_id}/builder/agent-contract`
- New backend contract builder now resolves the app-selected runtime agent and returns:
  - selected agent summary,
  - resolved tool contracts (input/output schemas),
  - unresolved tool reference diagnostics,
  - standardized optional UI hint metadata sourced from `x-ui` / `x_ui`.
- UI-hint standard is explicitly optional and normalized around:
  - `x-ui` key,
  - supported kinds: `chart`, `table`, `stat`.
- Coding-agent run creation now injects selected-agent contract data into run context:
  - `input_params.context.selected_agent_contract`
- Added coding-agent function tool:
  - `coding_agent_get_agent_integration_contract`
  - allows the coding runtime to fetch the latest selected-agent contract during implementation tasks.
- Added compact contract summary tool:
  - `coding_agent_describe_selected_agent_contract`
  - returns a bounded summary (agent metadata, resolved tools, runtime readiness, summarized input/output schema fields, optional unresolved refs).
- Coding-agent profile instructions now explicitly direct use of the contract tool when implementing runtime-agent integrations.
- Removed deterministic keyword-intent contract guard from run creation.
  - Contract retrieval is tool-driven (agent decides when to call contract tools) rather than forced by prompt keyword matching.
  - Selected-agent contract is still injected in run context/system message as baseline context.
- Added backend test coverage for tool-based retrieval path:
  - `backend/tests/coding_agent_api/test_agent_integration_contract_context.py`
  - validates compact summary output shape, schema truncation behavior, and optional unresolved-ref payload.

## Latest OpenCode Custom-Tool Bootstrap Updates (2026-02-21)
- Removed OpenCode-specific MCP contract tool registration path from runtime startup.
  - OpenCode startup no longer posts `/mcp` for selected-agent contract tooling.
  - OpenCode-specific MCP env surface was removed from active run path.
- Introduced canonical project-local OpenCode custom-tool bootstrap source:
  - `backend/app/templates/published_app_bootstrap/opencode/.opencode/package.json`
  - `backend/app/templates/published_app_bootstrap/opencode/.opencode/tools/coding_agent_get_agent_integration_contract.ts`
  - `backend/app/templates/published_app_bootstrap/opencode/.opencode/tools/coding_agent_describe_selected_agent_contract.ts`
- Template loader now overlays bootstrap files into all template outputs (`build_template_files`) so new app drafts include custom tools by default.
- OpenCode run startup now performs fail-closed workspace seeding before OpenCode session start:
  - seeds `.opencode/*` tool files (self-heal for legacy drafts),
  - writes run-scoped selected-agent contract context to `.cache/opencode/selected_agent_contract.json`,
  - fails run startup if bootstrap/context seeding fails (sandbox and host modes).
- OpenCode prompt guidance now always includes contract-tool instructions (no MCP availability gating).
- Added/updated OpenCode client test coverage for:
  - no `/mcp` calls in official mode start path,
  - workspace bootstrap seeding,
  - sandbox-mode fail-closed behavior on seed write failures.

## Latest Sandbox Start Timeout Fixes (2026-02-19)
- Draft-dev runtime client now uses a dedicated timeout for OpenCode run bootstrap calls:
  - env: `APPS_DRAFT_DEV_CONTROLLER_OPENCODE_START_TIMEOUT_SECONDS`
  - default behavior: max(`APPS_DRAFT_DEV_CONTROLLER_TIMEOUT_SECONDS`, `30s`).
- This avoids false client-side timeout on `/internal/sandbox-controller/sessions/{sandbox_id}/opencode/start` during slower OpenCode startup phases.
- Draft-dev runtime client now reports exception class names when timeout/transport exceptions have empty message text (prevents blank `Draft dev controller request failed:` errors).

## Latest Tool Transparency + Builder Task/Queue/Shimmer Updates (2026-02-19)
- Added explicit coding-agent capabilities API:
  - `GET /admin/apps/{app_id}/coding-agent/capabilities`
- Capabilities payload is backend-policy + registry derived and read-only:
  - `default_engine` (`native`/`opencode`) from backend policy.
  - `native_enabled` policy flag.
  - `native_tools` + `native_tool_count` from `CODING_AGENT_TOOL_SPECS` (`name`, `slug`, `function_name`).
  - `opencode_policy` transparency summary:
    - tooling delegated to upstream OpenCode,
    - repo-local bootstrap/custom-tools configured,
    - workspace permission model based on project-local custom tools + context file.
- Builder chat frontend now exposes capabilities summary in-panel so users can see the effective tool-access policy without guessing.
- Builder chat run orchestration now supports FIFO in-memory prompt queueing:
  - prompts submitted while a run is active are queued,
  - queued items can be removed individually,
  - terminal run states auto-dequeue the next item.
- Stop behavior now performs end-to-end cancellation:
  - backend cancel endpoint call (`POST /coding-agent/runs/{run_id}/cancel`),
  - local stream reader cancellation,
  - queue is preserved and continues with next queued prompt.
- Builder chat tool timeline migrated to AI Elements `Task` presentation:
  - normalized tool intent text,
  - path chip extraction from tool payload (`path`, `filePath`, `from_path`, `to_path`),
  - active row shimmer while tool is running.
- Builder chat now uses AI Elements `Queue` for pending prompts and `Shimmer` for active-step rendering.

## Latest Chat-Scoped Sandbox Reuse + Timing Telemetry Updates (2026-02-20)
- Added chat-scoped sandbox reuse policy for coding-agent runs:
  - run context now carries `sandbox_scope_key` derived from `chat_session_id` when enabled,
  - sandbox provisioning can reuse a stable controller session id (`chat-{chat_session_id}`) across runs.
- Added keep-warm lifecycle behavior for reusable chat-scoped sandboxes:
  - completed/cancelled/paused runs can refresh sandbox TTL instead of always hard-stopping the sandbox,
  - error-terminal runs still stop/fail closed.
- Added opportunistic TTL reaping for expired coding-run sandbox sessions during provisioning.
- Added structured timing metrics persisted in run context under `input_params.context.timing_metrics_ms`:
  - `create_run`,
  - `create_run_api`,
  - `sandbox_start`,
  - `opencode_start`,
  - `first_token`.
- Added runtime timing logs (`CODING_AGENT_TIMING ...`) so slow phases can be measured in production traces.

## OpenCode Validation Snapshot
- `cd backend && PYTHONPATH=. pytest tests/opencode_server_client -q` -> pass (`19 passed, 2 skipped`).
- `cd backend && OPENCODE_LIVE_TEST=1 OPENCODE_LIVE_FULL_TASK=1 APPS_CODING_AGENT_OPENCODE_BASE_URL=http://127.0.0.1:8788 OPENCODE_LIVE_MODEL_ID=opencode/gpt-5-nano PYTHONPATH=. pytest tests/opencode_server_client/test_opencode_server_client_live.py -q` -> pass (`2 passed`).
- `cd backend && PYTHONPATH=. pytest tests/coding_agent_api/test_run_lifecycle.py -q` -> pass (`24 passed`).

## Decision Record Preserved by This Merge
- Keep platform runtime primitives as source of truth.
- Keep coding-agent API/SSE contract as the stable external interface.
- Keep run-scoped model pinning and tool validation semantics.
- Keep OpenCode as default, with env-gated native fallback and fail-closed execution/error contracts.
