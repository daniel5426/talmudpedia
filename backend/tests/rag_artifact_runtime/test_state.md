Last Updated: 2026-04-21

# Test State

## Scope

RAG custom-operator artifact pinning and shared artifact runtime execution.

## Test Files Present

- `test_rag_artifact_runtime.py`

## Key Scenarios Covered

- tenant fixture access now comes from canonical `SecurityBootstrapService` owner assignments instead of membership-role fields
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
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_runtime_secret_service.py backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_artifact_versions_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py backend/tests/coding_agent_chat_history_api/test_chat_history_endpoints.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py`
- Date: 2026-04-21 Asia/Hebron
- Result: Fail early in `backend/tests/artifact_runtime/test_execution_service.py` on live artifact creation (`invalid input value for enum artifactownertype: "organization"`), so this feature did not get an isolated rerun in the combined pass.

## Known Gaps

- no API-level `/jobs` integration test yet
- no mixed builtin-plus-artifact pipeline coverage yet
