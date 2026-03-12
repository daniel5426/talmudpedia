# Platform Architect Artifact Tests

Last Updated: 2026-03-12

## Scope
- Platform Architect canonical artifact action contracts and artifact-coding delegation toolset.
- Seeded architect-only delegation tools for artifact coding session prepare/get-state and child-agent calls.

## Test Files Present
- test_architect_artifact_delegation.py

## Key Scenarios Covered
- `platform-assets` exposes canonical artifact actions and removes the legacy draft mutation action.
- Architect runtime instructions describe the artifact-coding delegation flow.
- Architect-only delegation tools seed as published global tools with the expected implementation types.
- `artifact-coding-agent-call` now routes through `ArtifactCodingRuntimeService.start_prompt_run()` instead of the generic `agent_call` executor.
- Delegation call coverage verifies the prepared `chat_session_id` is passed into the runtime-service path and the returned run stays on the `artifact_coding_agent` surface.
- Architect artifact-coding delegation now normalizes wrapped `query`/`value` payloads and can recover the latest artifact-coding session for the same tenant/user when `chat_session_id` is omitted by the model.

## Last Run
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_artifacts`
- Date: 2026-03-12 00:57 EET
- Result: passed (`5 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_artifacts/test_architect_artifact_delegation.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date: 2026-03-12 03:55 EET
- Result: passed (`10 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_architect_artifacts/test_architect_artifact_delegation.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_runtime/test_architect_seeding.py`
- Date: 2026-03-12 04:05 EET
- Result: passed (`12 passed, 5 warnings`)

## Known Gaps
- No full live architect run yet validates the complete delegation-save-publish flow through the seeded graph.
