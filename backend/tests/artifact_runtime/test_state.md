Last Updated: 2026-03-10

# Test State

## Scope

Artifact runtime revision and bundle lifecycle.

## Test Files Present

- `test_revision_service.py`
- `test_execution_service.py`

## Key Scenarios Covered

- create tenant artifact draft with bundled runtime payload
- update artifact and create a new draft revision
- publish the latest draft revision
- verify bundle builder hash stability
- verify dependency hash persistence and dependency-aware bundle contents
- verify runtime bundle ships `dependencies.json` and bundled runner support
- create live artifact runs for `agent` and `rag` domains
- enforce published-only execution for live domains
- route background live runs to the configured queue class
- preserve raw JSON input payloads through the runner compatibility path

## Last Run

- Command: `python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py`
- Date: 2026-03-10
- Result: Pass (2 passed)
- Command: `PYTHONPATH=backend python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py -q`
- Date: 2026-03-10 22:09 EET
- Result: Pass (19 passed)

## Known Gaps

- no object-storage-backed bundle upload integration coverage yet
- no migration script execution coverage yet
- no local bootstrap helper coverage yet
