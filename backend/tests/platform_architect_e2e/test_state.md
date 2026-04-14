# Platform Architect E2E Tests State

Last Updated: 2026-04-15

## Scope of the feature
Live end-to-end validation of the seeded `platform-architect` agent against the full domain action matrix, with API and DB-backed evidence checks.

## Test files present
- `test_architect_e2e_live.py`
- `test_live_harness.py`
- `scenario_matrix.py`
- `verifiers.py`
- `db_checks.py`
- `reporting.py`

## Key scenarios covered
- Parameterized matrix over all actions declared in `PLATFORM_ARCHITECT_DOMAIN_TOOLS`.
- Per-scenario architect run, action-evidence checks, expected block-code validation, and side-effect spot checks.
- DB linkage check for generated `agent_runs` rows.
- Session report persisted as JSON for run review.
- Session preflight validates delegated scope coverage (required action scopes vs architect workload policy and initiator effective scopes) before running matrix scenarios.
- Architect run start now sends explicit `context.requested_scopes` derived from scenario matrix required scopes to stabilize delegated grant minting.
- Artifact-create side-effect verification now checks canonical artifact metadata like `display_name` for `artifacts.create`.
- Optional/manual live smoke coverage now exists for the architect artifact-worker flow behind `ARCH_E2E_ARTIFACT_WORKER_SMOKE=1`.
- Live harness support now exists outside pytest through `backend/scripts/platform_architect_live_harness.py`, with queue/watch mode and persisted JSON run bundles.
- The live harness now self-bootstraps local auth from the real DB when env auth is missing, and persists both full forensic bundles and compact summary bundles.

## Last run command + date/time + result
- Command: `cd backend && TEST_USE_REAL_DB=1 pytest -q tests/platform_architect_e2e/test_architect_e2e_live.py -m real_db`
- Date/Time: 2026-03-05 (local run during this change set)
- Result: partial pass baseline after scope remediation (`9 passed, 35 failed, 1 warning`, ~5m03s). Scope/delegation run-start blocker is cleared; remaining failures are action-level (missing required payload fields, unsupported action/schema mismatches, and side-effect assertions).
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_e2e/test_live_harness.py`
- Date/Time: 2026-04-15 01:18 EEST
- Result: passed (`7 passed, 1 warning`)

## Known gaps or follow-ups
- Add dedicated live E2E scenarios for `agents.nodes.catalog`, `agents.nodes.schema`, and `agents.nodes.validate` to verify architect preflight/repair loops in real tenant data.
- Action attempt detection relies on run payload/tree textual evidence; schema-specific trace extraction can be tightened after observing live payloads.
- Some governance outcomes depend on caller role/policy state and are asserted primarily via expected block-code presence.
- Remaining failing scenarios are concentrated in strict side-effect checks plus schema/action mismatches (especially governance/workload actions) and missing action-specific prerequisites for read/query scenarios.
- Preflight depends on decoding JWT `sub` for initiator scope intersection details; opaque tokens without JWT claims degrade to policy-only scope diagnostics.
- The artifact-worker smoke test is opt-in/manual and is not part of the matrix baseline command.
- The live harness persists raw run bundles plus compact summary bundles; the summary should be the default diagnosis surface for iterative Codex loops, with the raw bundle reserved for deeper forensics.
