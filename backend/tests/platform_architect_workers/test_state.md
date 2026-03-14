# Platform Architect Workers Tests State

Last Updated: 2026-03-14

## Scope of the feature
Focused coverage for the architect-specific async worker runtime, binding-backed artifact delegation flow, and seeded architect DB-backed orchestration behavior.

## Test files present
- `test_worker_runtime.py`
- `test_architect_worker_integration.py`

## Key scenarios covered
- Worker tool seeding and prompt/tool-surface assertions for the seeded architect.
- Lightweight `architect-worker-binding-prepare` create flow uses `title_prompt + draft_seed.kind`, while advanced full snapshot seeding is isolated to `seed_snapshot`.
- Async worker runtime behavior including duplicate-binding rejection in group spawn.
- Child-run inspection returning binding metadata from run records.
- DB-backed seeded architect run that prepares an artifact binding, spawns an artifact worker, waits, exports binding state, and persists the canonical artifact successfully.
- DB-backed seeded architect run that attempts a second mutating spawn on the same binding and reports the active-binding blocker cleanly.
- Strict architect worker tool schemas reject malformed model payloads before runtime dispatch, including the observed bad binding-create guesses (`create`, `files`, `entrypoint`, `text`), while still allowing executor-owned runtime metadata to flow separately.
- Binding-exported artifact payloads stay compatible with strict `platform-assets` schemas by omitting unused kind contracts.

## Last run command + date/time + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py`
- Date/Time: 2026-03-14 20:39 EET
- Result: PASS (`89 passed`)

## Known gaps or follow-ups
- Group fanout is covered at runtime level, but there is not yet a DB-backed seeded architect E2E for parallel multi-binding spawn/join.
- Live real-DB smoke coverage exists separately in `backend/tests/platform_architect_e2e/` and remains opt-in/manual.
