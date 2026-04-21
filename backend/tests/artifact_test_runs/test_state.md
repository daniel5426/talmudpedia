Last Updated: 2026-04-21

# Test State

## Scope

Artifact test-run APIs and queued execution lifecycle on the modern run-based artifact runtime.

## Test Files Present

- `test_artifact_test_run_api.py`

## Key Scenarios Covered

- tenant fixture access now comes from canonical `SecurityBootstrapService` owner assignments instead of membership-role fields
- create artifact through the new tenant artifact CRUD path
- create artifact through the tenant artifact CRUD path without a user-authored slug
- execute a run-based artifact test and inspect run/events APIs
- execute only the run-based `/admin/artifacts/test-runs` surface; the legacy wrapper is removed
- execute an unsaved `/admin/artifacts/test-runs` request without `tenant_slug` by using principal tenant context
- cancel a queued test run
- return runtime queue status for artifact-page test runs
- return HTTP 429 when eager artifact-page test execution hits tenant capacity
- return structured `422` validation errors when `execute(inputs, config, context)` is missing
- return structured `429` rate-limit payloads when tenant capacity is exhausted
- return HTTP 200 with a failed run id when eager artifact-page dispatch crashes after run creation
- resolve or reuse a `staging` deployment and dispatch through the Cloudflare runtime path
- assert artifact-page test runs stay on `domain="test"` and `queue_class="artifact_test"`
- pass artifact-page test input through as the raw worker `inputs` payload
- keep queued-cancel coverage isolated from real deploy/dispatch by stubbing enqueue at the test boundary

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
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-11 18:18 EET
- Result: Pass (3 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-16 19:41 EET
- Result: Pass (`3 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (5 passed, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (34 passed, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (21 passed, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_test_runs/test_artifact_test_run_api.py -k execute_contract_error`
- Date: 2026-03-27 Asia/Hebron
- Result: Pass
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-04-14 Asia/Hebron
- Result: Pass (`7 passed, 8 warnings`)
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_runtime_secret_service.py backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_artifact_versions_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/apps_builder_sandbox_runtime/test_draft_dev_runtime_lifecycle.py backend/tests/coding_agent_chat_history_api/test_chat_history_endpoints.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py`
- Date: 2026-04-21 Asia/Hebron
- Result: Fail early in `backend/tests/artifact_runtime/test_execution_service.py` on live artifact creation (`invalid input value for enum artifactownertype: "organization"`), so this feature did not get an isolated rerun in the combined pass.

## Known Gaps

- no frontend polling coverage yet
- no running-process cancellation coverage yet
