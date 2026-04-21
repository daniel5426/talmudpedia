Last Updated: 2026-04-21

# Test State

## Scope

Agent artifact-node production pinning and tenant artifact execution routing.

## Test Files Present

- `test_agent_artifact_runtime.py`

## Key Scenarios Covered

- tenant fixture access now comes from canonical `SecurityBootstrapService` owner assignments instead of membership-role fields
- production compile pins `_artifact_revision_id` for tenant artifact nodes
- production compile rejects draft-only tenant artifacts
- tenant artifact node execution delegates to `ArtifactExecutionService`
- graph analysis derives tenant artifact node output contracts from `agent_contract.output_schema`

## Last Run

- Command: `PYTHONPATH=backend python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py -q`
- Date: 2026-03-11 03:35 Asia/Hebron
- Result: Pass (22 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py backend/tests/platform_sdk_tool backend/tests/control_plane_sdk/test_client_and_modules.py`
- Date: 2026-03-11 18:18 EET
- Result: Pass (127 passed, 11 skipped)
- Command: `pytest -q backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py`
- Date: 2026-03-22
- Result: Pass (4 tests)
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_runtime_secret_service.py backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_artifact_versions_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py backend/tests/coding_agent_chat_history_api/test_chat_history_endpoints.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py`
- Date: 2026-04-21 Asia/Hebron
- Result: Fail early in `backend/tests/artifact_runtime/test_execution_service.py` on live artifact creation (`invalid input value for enum artifactownertype: "organization"`), so this feature did not get an isolated rerun in the combined pass.
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py::test_artifact_node_executor_routes_tenant_artifacts_through_shared_runtime`
- Date: 2026-04-21 Asia/Hebron
- Result: Pass (`1 passed, 7 warnings`)

## Known Gaps

- no end-to-end agent run coverage for tenant artifact nodes yet
- no end-to-end convert-kind coverage for agent-node artifacts yet
