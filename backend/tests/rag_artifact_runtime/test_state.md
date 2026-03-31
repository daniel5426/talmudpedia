Last Updated: 2026-03-31

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
- executable pipelines now require a backing `VisualPipeline` row in test setup, matching the live DB schema

## Last Run

- Command: `PYTHONPATH=backend python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py -q`
- Date: 2026-03-11 02:38 Asia/Hebron
- Result: Pass (19 passed)

- Command: `PYTHONPATH=backend python3 -m pytest -q -rsxX backend/tests/rag_artifact_runtime`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (`4 passed`). The suite now seeds `VisualPipeline` rows explicitly before inserting `ExecutablePipeline`, matching the current foreign-key requirements.

## Known Gaps

- no API-level `/jobs` integration test yet
- no mixed builtin-plus-artifact pipeline coverage yet
