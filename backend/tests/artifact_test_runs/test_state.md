Last Updated: 2026-03-11

# Test State

## Scope

Artifact test-run APIs and queued execution lifecycle on the modern run-based artifact runtime.

## Test Files Present

- `test_artifact_test_run_api.py`

## Key Scenarios Covered

- create artifact through the new tenant artifact CRUD path
- execute a run-based artifact test and inspect run/events APIs
- verify `POST /admin/artifacts/test` remains a thin wrapper over the same run-based runtime path
- execute an unsaved `/admin/artifacts/test-runs` request without `tenant_slug` by using principal tenant context
- cancel a queued test run
- resolve or reuse a `staging` deployment and dispatch through the Cloudflare runtime path
- assert artifact-page test runs stay on `domain="test"` and `queue_class="artifact_test"`

## Last Run

- Command: `python3 -m pytest backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-10
- Result: Pass (3 passed)
- Command: `PYTHONPATH=backend python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py -q`
- Date: 2026-03-11 02:38 Asia/Hebron
- Result: Pass (19 passed)
- Command: `PYTHONPATH=backend python3 -m pytest backend/tests/artifact_test_runs/test_artifact_test_run_api.py -q`
- Date: 2026-03-11 03:20 Asia/Hebron
- Result: Pass (3 passed)

## Known Gaps

- no frontend polling coverage yet
- no running-process cancellation coverage yet
