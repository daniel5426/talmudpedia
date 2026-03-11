Last Updated: 2026-03-11

# Test State

## Scope

Agent artifact-node production pinning and tenant artifact execution routing.

## Test Files Present

- `test_agent_artifact_runtime.py`

## Key Scenarios Covered

- production compile pins `_artifact_revision_id` for tenant artifact nodes
- production compile rejects draft-only tenant artifacts
- tenant artifact node execution delegates to `ArtifactExecutionService`

## Last Run

- Command: `PYTHONPATH=backend python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py -q`
- Date: 2026-03-11 03:35 Asia/Hebron
- Result: Pass (22 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py backend/tests/platform_sdk_tool backend/tests/control_plane_sdk/test_client_and_modules.py`
- Date: 2026-03-11 18:18 EET
- Result: Pass (127 passed, 11 skipped)

## Known Gaps

- no end-to-end agent run coverage for tenant artifact nodes yet
- no end-to-end convert-kind coverage for agent-node artifacts yet
