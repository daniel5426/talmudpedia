Last Updated: 2026-03-10

# Test State

## Scope

Artifact test-run APIs, queued execution lifecycle, and compatibility path.

## Test Files Present

- `test_artifact_test_run_api.py`

## Key Scenarios Covered

- create artifact through the new tenant artifact CRUD path
- execute a run-based artifact test and inspect run/events APIs
- verify legacy `/admin/artifacts/test` uses the new runtime path
- cancel a queued test run
- exercise HTTP worker mode against the artifact worker API with a mocked sandbox adapter
- assert artifact-page test runs stay on `domain="test"` and `queue_class="artifact_test"`

## Last Run

- Command: `python3 -m pytest backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-10
- Result: Pass (3 passed)
- Command: `PYTHONPATH=backend python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py -q`
- Date: 2026-03-10 22:09 EET
- Result: Pass (19 passed)

## Known Gaps

- no frontend polling coverage yet
- no running-process cancellation coverage yet
