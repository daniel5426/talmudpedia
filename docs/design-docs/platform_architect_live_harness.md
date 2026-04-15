# Platform Architect Live Harness

Last Updated: 2026-04-15

## Purpose
Provide a real-runtime harness for driving the seeded `platform-architect` agent against a live tenant, capturing full run artifacts, and supporting long-running task queues without using the UI.

This is not a unit-test harness. It is a developer/operator loop for:
- sending real prompts to the architect
- polling real runs to terminal state
- fetching persisted run events and run tree data
- saving reproducible run bundles for later diagnosis and fixes

## Core Pieces
- Service module: [backend/app/services/platform_architect_live_harness.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/platform_architect_live_harness.py)
- CLI entrypoint: [backend/scripts/platform_architect_live_harness.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/scripts/platform_architect_live_harness.py)
- Existing live E2E package: [backend/tests/platform_architect_e2e](/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/platform_architect_e2e)

## Runtime Contract
The harness talks to the real backend through:
- `POST /agents/{agent_id}/run`
- `GET /agents/runs/{run_id}`
- `GET /agents/runs/{run_id}/tree`
- `GET /agents/runs/{run_id}/events`
- `GET /agents?limit=100&view=summary` to resolve `platform-architect` when `PLATFORM_ARCHITECT_AGENT_ID` is not set

## Environment
Preferred env vars:
- `PLATFORM_ARCHITECT_BASE_URL`
- `PLATFORM_ARCHITECT_API_KEY`
- `PLATFORM_ARCHITECT_TENANT_ID`
- `PLATFORM_ARCHITECT_AGENT_ID`
- `PLATFORM_ARCHITECT_TIMEOUT_SECONDS`
- `PLATFORM_ARCHITECT_OUTPUT_DIR`

Fallback compatibility reads:
- `TEST_BASE_URL`
- `TEST_API_KEY`
- `TEST_TENANT_ID`

Local dev bootstrap:
- if auth env is missing, the CLI discovers a real local tenant/user pair from Postgres and mints a local JWT with wildcard scopes
- architect runs default to `context.architect_mode="full_access"` and `context.execution_mode="debug"` unless overridden

## CLI Modes
### One-shot prompt
Run a single live architect prompt and persist a full bundle:

```bash
cd /Users/danielbenassaya/Code/personal/talmudpedia
PYTHONPATH=backend python3 backend/scripts/platform_architect_live_harness.py prompt \
  --prompt "create an agent called faq-bot" \
  --context-json '{"architect_mode":"full_access"}'
```

### Queue mode
Process a JSON array or JSONL task file:

```bash
cd /Users/danielbenassaya/Code/personal/talmudpedia
PYTHONPATH=backend python3 backend/scripts/platform_architect_live_harness.py queue \
  --tasks-file backend/artifacts/platform_architect_live/tasks.jsonl \
  --watch \
  --poll-seconds 15
```

Task shape:

```json
{"id":"agents-create-shell","prompt":"create an agent named faq-bot","runtime_context":{"architect_mode":"full_access"},"timeout_s":300,"tags":["agents","create"]}
```

## Output
Each completed task persists two JSON artifacts under `backend/artifacts/platform_architect_live/` by default:
- full forensic bundle
- compact summary bundle for Codex/agent diagnosis loops

Bundle includes:
- prompt
- run id
- final run payload
- run tree
- persisted run events
- extracted assistant text
- compact event summary with tool start/end evidence

Queue mode also maintains `processed_tasks.json` so the same task file can be watched for hours without rerunning completed entries.

The compact summary keeps:
- assistant text
- compact final-run metadata
- event counts
- compact tool call input/output previews

This avoids feeding multi-hundred-KB raw event bundles back into the next diagnosis step unless full forensics are needed.

## Intended Loop
1. Start backend and Celery against the target local/runtime environment.
2. Feed prompts or a watched task queue into the harness.
3. Inspect saved bundles, not chat screenshots.
4. Patch code/contracts.
5. Rerun the same live task until behavior is acceptable.
6. Move to the next task.

This gives Codex or any other coding agent a stable non-UI integration surface for live architect improvement work.

## Closed-Loop Improvement Mode
Use this harness as an autonomous control-plane improvement loop, not just a one-off runner.

Session expectations:
- work in phases, not random prompts
- start each phase with simple tool-use prompts
- then move to richer multi-step prompts
- end the phase with real production-like creation flows

Recommended prompt progression per phase:
1. direct reads
   - examples: list models, list tools, list agents
2. focused mutations
   - examples: create shell, update graph, attach tool, create knowledge store
3. realistic workflows
   - examples: create a draft agent from scratch, create a RAG pipeline, wire agent + pipeline + store

For every phase:
- queue multiple tasks
- persist both full and summary bundles
- keep an explicit log of:
  - prompts that succeeded
  - prompts that failed
  - normalized failure reason
  - suspected contract/harness gap
- reason over the stored results before changing code
- choose the smallest high-value refactor that improves the most failing prompts
- implement the fix
- rerun failed prompts first
- if the failures are resolved, promote those prompts to the success set
- then move to the next phase and repeat

## Prompt Log Discipline
Do not rely on memory or chat history. Keep a durable task/result log alongside the task queue.

Each task should capture at minimum:
- `id`
- `phase`
- `prompt`
- `tags`
- expected intent such as `read`, `mutation`, `workflow`

Each completed result should capture at minimum:
- `task_id`
- `run_id`
- terminal status
- whether the objective succeeded
- normalized failure code if not
- short reason summary
- fix candidate or follow-up decision

The compact summary bundle should be the default diagnosis surface for this log. Use the full forensic bundle only when the summary is insufficient.

## Refactor Decision Rule
After each batch:
- group failures by shared root cause
- prefer contract/harness fixes over prompt-only work
- prefer fixes that improve multiple prompts or an entire action family
- rerun the failed batch before expanding scope

Only after a phase is stable should the next phase begin.

## Practical Goal
The target is a repeated loop:
- run live tasks
- store evidence
- classify failures
- refactor tools/harness
- retest failed tasks
- confirm improvement
- advance to the next capability phase

That is the intended environment for autonomously hardening the control-plane tools for both `platform-architect` and future MCP/public-programmatic use.

## Multi-Agent Orchestration
This loop can be upgraded to multi-agent execution, but only with strict ownership of files and phases.

Recommended pattern:
- one coordinator agent owns the campaign plan and decides phase order
- one worker agent per phase or per failure cluster
- workers do not share writable markdown files
- workers only write inside their assigned phase folder
- only the coordinator updates shared rollup files
- all subagents should run with `gpt-5.4`
- all subagents should use `high` reasoning
- keep subagent execution in fast operator mode: short outputs, action-biased, no long narrative
- default to a broad first wave, not a minimal one
- for an active campaign, prefer spawning `4-6` workers in the first batch when the phases are independent enough

Good split:
- worker A: simple reads and list-contract prompts
- worker B: mutation prompts
- worker C: realistic workflow prompts
- worker D: agent authoring workflows
- worker E: RAG and knowledge-store workflows
- worker F: runtime execution and orchestration workflows
- coordinator: compares results, chooses refactors, decides retest order

Bad split:
- multiple workers appending to the same findings file
- multiple workers editing the same phase task file
- workers deciding global campaign state independently

## Shared File Layout
Use a phase-scoped structure so writes are isolated:

```text
backend/artifacts/platform_architect_live/
  campaign.md
  phase_index.json
  phase-01/
    tasks.jsonl
    results.jsonl
    coordinator_decision.md
    worker-a.md
    worker-b.md
    bundles/
  phase-02/
    ...
```

Ownership rules:
- `campaign.md`: coordinator only
- `phase_index.json`: coordinator only
- `phase-XX/tasks.jsonl`: coordinator only
- `phase-XX/results.jsonl`: append-only by coordinator after reading worker outputs
- `phase-XX/coordinator_decision.md`: coordinator only
- `phase-XX/worker-*.md`: exactly one worker per file
- `phase-XX/bundles/`: harness output only

## Multi-Agent Loop
Per phase:
1. coordinator defines the task batch
2. each worker runs its assigned prompts through the harness
3. each worker writes findings only to its own file
4. coordinator reads worker files and summary bundles
5. coordinator groups failures by root cause
6. coordinator decides the best refactor
7. fixes are implemented
8. failed prompts are rerun first
9. if stable, the coordinator opens the next phase

When possible, open larger capability phases instead of tiny narrow ones. Prefer:
- read/discovery surface
- mutation/create surface
- agent authoring
- RAG/pipeline authoring
- runtime execution
- orchestration/worker surface

## Coordination Rule
Use subagents for breadth, not for shared-state mutation.

That means:
- parallelize prompt execution and failure analysis
- centralize plan updates and pass/fail promotion in one coordinator
- keep raw run artifacts append-only
- keep markdown ownership explicit per worker
- do not let worker agents plan or implement broad shared fixes independently
- fix planning must happen only after the coordinator has reviewed all worker findings together
- implementation sequencing for shared fixes must be centralized, even if later execution work is delegated in slices

This avoids merge noise, conflicting conclusions, and broken phase history while still letting the loop run in parallel for hours.
