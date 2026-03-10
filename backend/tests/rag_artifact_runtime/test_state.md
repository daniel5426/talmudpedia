Last Updated: 2026-03-10

# Test State

## Scope

RAG custom-operator artifact pinning and shared artifact runtime execution.

## Test Files Present

- `test_rag_artifact_runtime.py`

## Key Scenarios Covered

- custom operator sync resolves `legacy_custom_operator_id -> Artifact`
- pipeline compile pins `artifact_revision_id` for published artifact-backed operators
- publish/compile rejects artifact-backed operators without a published revision
- pipeline executor routes artifact steps through `ArtifactExecutionService`
- retrieval runtime uses `artifact_prod_interactive` for inline execution

## Last Run

- Command: `PYTHONPATH=backend python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py -q`
- Date: 2026-03-10 22:09 EET
- Result: Pass (19 passed)

## Known Gaps

- no API-level `/jobs` integration test yet
- no mixed builtin-plus-artifact pipeline coverage yet
