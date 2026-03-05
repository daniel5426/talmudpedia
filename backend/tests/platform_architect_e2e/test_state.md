# Platform Architect E2E Tests State

Last Updated: 2026-03-05

## Scope of the feature
Live end-to-end validation of the seeded `platform-architect` agent against the full domain action matrix, with API and DB-backed evidence checks.

## Test files present
- `test_architect_e2e_live.py`
- `scenario_matrix.py`
- `verifiers.py`
- `db_checks.py`
- `reporting.py`

## Key scenarios covered
- Parameterized matrix over all actions declared in `PLATFORM_ARCHITECT_DOMAIN_TOOLS`.
- Per-scenario architect run, action-evidence checks, expected block-code validation, and side-effect spot checks.
- DB linkage check for generated `agent_runs` rows.
- Session report persisted as JSON for run review.

## Last run command + date/time + result
- Command: `cd backend && TEST_USE_REAL_DB=1 pytest -q tests/platform_architect_e2e/test_architect_e2e_live.py -k agents_create -m real_db`
- Date/Time: 2026-03-05 (local run during this change set)
- Result: fail (`1 failed, 43 deselected`) with side-effect assertion `No created agent with expected prefix`.

## Known gaps or follow-ups
- `agents.validate` endpoint currently returns placeholder-valid in service layer; this limits strict graph correctness assertions.
- Action attempt detection relies on run payload/tree textual evidence; schema-specific trace extraction can be tightened after observing live payloads.
- Some governance outcomes depend on caller role/policy state and are asserted primarily via expected block-code presence.
- Remaining failing scenarios are concentrated in strict side-effect and expected-block-code assumptions (create-prefix assertions and orchestration/publish block code expectations).
