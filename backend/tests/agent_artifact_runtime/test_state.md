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
- Date: 2026-03-11 02:38 Asia/Hebron
- Result: Pass (19 passed)

## Known Gaps

- no end-to-end agent run coverage for tenant artifact nodes yet
- builtin repo artifact compatibility remains unit-tested indirectly only
