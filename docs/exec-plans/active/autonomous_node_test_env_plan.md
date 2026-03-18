# Execution Plan: Autonomous Node Test Environment

Last Updated: 2026-03-18

## Status: Planned

This plan defines the environment required to build, run, monitor, iterate, and harden an extreme test matrix around every current node contract.

## Scope

For this plan, "node" means runtime-executable graph units across the current platform, especially:
- agent graph nodes
- tool invocation nodes
- RAG pipeline operators/nodes
- node-to-node contract boundaries

This plan is about the test environment and autonomous workflow, not yet the full test inventory itself.

## Goal

Create an environment where Codex can autonomously:
- add node-level tests
- run them in tight loops
- inspect traces and failures
- patch code or tests
- rerun focused and broad suites
- detect flakes and contract drift
- keep docs and test-state files current

## Core Requirement

The environment must optimize for determinism first, breadth second.

If a test environment is broad but nondeterministic, autonomous iteration will burn time on noise instead of finding real defects. The first cut must therefore favor:
- isolated state
- reproducible fixtures
- stable service dependencies
- explicit contracts
- strong observability

## Environment Strategy

### 1. Dedicated Test Profiles

Add explicit test env profiles instead of reusing developer env files.

Target:
- `backend/.env.test`
- `frontend-reshet/.env.test`
- optional `docker-compose.test.yml` or equivalent test-stack bootstrap

Rules:
- no shared developer DBs
- no shared Redis state
- no implicit fallback to local dev secrets
- no tests that silently hit production-like external services unless the suite explicitly opts in

### 2. Hermetic Local Core Stack

Every autonomous loop needs a disposable local core stack:
- Postgres
- Redis
- backend API
- any required worker/runtime process
- local artifact/runtime dependencies that are part of the normal code path

Requirements:
- one-command boot
- one-command reset
- one-command teardown
- health checks before test start
- clear failure if a dependency is unavailable

### 3. External Dependency Policy

Node tests should not primarily depend on live third-party providers.

Default strategy:
- mock or stub external LLM/search/MCP/network integrations
- use recorded or synthetic fixtures for deterministic contract validation
- keep a smaller opt-in live-provider verification suite separate from the main autonomous loop

The autonomous loop should spend most of its time in:
- unit-contract mode
- local integration mode
- replay/golden mode

Not in:
- credit-sensitive live-provider mode
- rate-limit-sensitive mode
- internet-fragile mode

### 4. Deterministic Fixture System

Node tests need stable fixture inputs and stable expected outputs.

Required fixture categories:
- canonical valid payloads per node/input schema
- boundary payloads
- malformed payloads
- partial payloads
- cross-node handoff payloads
- persisted-state fixtures
- golden trace/output fixtures where output shape is the contract

Rules:
- fixtures must be named by node and contract intent
- fixture updates must be explicit, never silent
- if golden outputs change, the diff must be reviewable

### 5. Node Harness Layer

We need a reusable harness so tests do not each rebuild setup ad hoc.

The harness should provide:
- graph/node factory helpers
- seeded DB/session helpers
- execution context builders
- tool binding builders
- fake provider adapters
- trace capture helpers
- assertion helpers for node outputs, events, and state transitions

This is the layer that lets Codex add many tests quickly without creating test chaos.

### 6. Observability For Autonomous Debugging

Every failing node test should produce enough evidence for Codex to self-correct.

Required signals:
- execution trace events
- node input resolution snapshots
- emitted output payloads
- tool call metadata
- contract validation errors
- DB side effects when relevant
- worker/runtime logs for async paths

Preferred existing backbone:
- shared execution-event logging via `backend/app/agent/execution/trace_recorder.py`

The test harness should collect and expose these artifacts directly in failures.

### 7. Flake Detection And Rerun Policy

The autonomous loop must distinguish deterministic regressions from flaky tests.

Requirements:
- rerun-once policy for suspect failures
- mark known flaky signatures explicitly
- track flake rate per suite
- fail hard on new flakes in core node-contract suites

The target is not "ignore flakes". The target is "detect them fast and drive them to zero."

### 8. Fast Loop + Broad Loop Split

We need two main execution modes.

Fast loop:
- focused node/unit/contract suites
- sub-minute target where possible
- used during local autonomous patching

Broad loop:
- cross-node integration suites
- compile/execute end-to-end graph slices
- async worker paths
- broader regression sweeps before closeout

Codex should default to fast-loop iteration, then promote to broad-loop verification.

## Test Taxonomy To Support

The environment must support all of these test classes cleanly:

### A. Contract Tests
- input schema validation
- output schema validation
- defaulting behavior
- forbidden field rejection
- type coercion rejection where contracts are strict

### B. Behavioral Node Tests
- happy path execution
- boundary conditions
- null/empty cases
- branching behavior
- retryable failure handling
- terminal failure handling

### C. Interaction Tests
- node A output into node B input
- tool-node to downstream consumer contracts
- agent graph to tool execution contracts
- RAG operator chain handoff contracts

### D. Persistence And Side-Effect Tests
- DB writes
- artifact revision binding
- runtime state transitions
- published/executable pointer updates
- idempotency where required

### E. Async And Runtime Tests
- worker execution
- task retries
- polling/streaming paths
- timeout handling
- cancellation and interruption paths

### F. Fault-Injection Tests
- provider timeout
- malformed provider response
- missing dependency
- stale binding
- corrupted persisted state
- partial downstream failure

## Environment Deliverables

Before the large-scale node test campaign, the environment should provide:

1. Dedicated test env files and boot scripts.
2. Disposable DB/Redis/runtime reset flow.
3. Shared node-test harness under `backend/tests/`.
4. Shared fake-provider layer.
5. Trace/log capture wired into test failures.
6. A broad-vs-fast test command map.
7. A documented policy for live-provider verification suites.
8. Coverage and flake reporting that can be compared over time.

## Autonomous Codex Workflow

The environment should support this exact loop:

1. Select one node or one interaction boundary.
2. Generate or extend fixtures for every meaningful input class.
3. Add strict contract tests first.
4. Add behavioral tests second.
5. Add cross-node interaction tests third.
6. Run the smallest relevant fast loop.
7. Inspect trace/log/DB evidence on failure.
8. Patch code or harness.
9. Rerun the focused suite until stable.
10. Promote to the relevant broad regression suite.
11. Update feature `test_state.md`.
12. Update plan/spec docs when contract reality changes.

## Phased Rollout

### Phase 0: Inventory And Scope Lock

Deliverables:
- canonical inventory of current node types
- canonical inventory of node contracts and handoff boundaries
- classification of which dependencies can be stubbed vs must be run locally

Exit criteria:
- no major node category is unaccounted for

### Phase 1: Test Environment Hardening

Deliverables:
- `.env.test` profiles
- test-stack bootstrap/reset scripts
- isolated DB/Redis/runtime configuration
- initial trace capture plumbing for tests

Exit criteria:
- a fresh machine or clean workspace can boot the test stack deterministically

### Phase 2: Shared Harness And Fixture System

Deliverables:
- reusable builders/helpers
- deterministic fake-provider adapters
- fixture conventions
- golden-output management rules

Exit criteria:
- new node tests can be added with minimal bespoke setup

### Phase 3: Node Contract Sweep

Deliverables:
- per-node contract suites
- boundary and malformed-input coverage
- output and side-effect assertions

Exit criteria:
- every current node has baseline contract coverage

### Phase 4: Interaction Matrix Sweep

Deliverables:
- pairwise node interaction suites
- graph-slice integration suites
- async/runtime transition suites

Exit criteria:
- all critical node handoff paths are covered

### Phase 5: Fault Injection And Flake Eradication

Deliverables:
- timeout/failure-path suites
- dependency-outage simulations
- rerun/flake reporting

Exit criteria:
- core node suites are stable and trusted for autonomous iteration

## Non-Goals

This plan does not assume:
- full dependence on live commercial APIs for every run
- broad compatibility shims for legacy behavior
- permissive contract recovery paths

The target is strict, explicit, production-grade behavior with minimal fallback noise.

## Risks

- "Node" is currently a cross-domain term and needs a locked inventory before test explosion begins.
- Live providers with weak credits or rate limits can poison autonomous iteration if they remain in the default loop.
- Existing test utilities may be too fragmented for the scale we want.
- Some async/runtime paths may currently be under-instrumented for self-debugging.

## Immediate Next Slice

After approving this plan, the first implementation slice should be:
- build the node inventory
- define the test env profile files and bootstrap commands
- create the shared harness skeleton
- wire trace capture into the first target feature suite
