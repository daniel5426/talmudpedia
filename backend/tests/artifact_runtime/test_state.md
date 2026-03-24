Last Updated: 2026-03-24

# Test State

## Scope

Artifact runtime revision and bundle lifecycle.

## Test Files Present

- `test_revision_service.py`
- `test_execution_service.py`
- `test_outbound_auth_service.py`
- `test_artifact_versions_api.py`
- `test_artifact_working_draft_api.py`

## Key Scenarios Covered

- create tenant artifact draft with source-tree runtime payload
- create tenant artifact draft without a user-authored slug
- update artifact and create a new draft revision
- skip draft revision creation for no-op artifact saves
- publish the latest draft revision
- list saved artifact revisions through the admin API
- fetch one historical artifact revision snapshot through the admin API
- read and update the persisted artifact working-draft snapshot through the admin API
- verify bundle builder hash stability
- verify build-hash stability across source-tree revisions
- verify Cloudflare package builder emits a runnable `main.py` worker entrypoint
- serialize free-plan worker module-load crashes as JSON detail payloads
- support package-style multi-file imports in the free-plan worker loader
- resolve Cloudflare deployment/dispatch flow for live runs
- create live artifact runs for `agent` and `rag` domains
- enforce published-only execution for live domains
- route background live runs to the configured queue class
- issue run-scoped outbound grants without persisting raw secrets in run payloads
- resolve brokered outbound auth headers from source-level credential references
- reject unreferenced credentials, invalid grants, and disallowed outbound hosts
- reject artifact handlers that do not implement the canonical three-argument contract
- include source-tree payloads in the free-plan standard-worker test mode

## Last Run

- Command: `python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py`
- Date: 2026-03-10
- Result: Pass (2 passed)
- Command: `PYTHONPATH=backend python3 -m pytest backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py -q`
- Date: 2026-03-11 03:35 Asia/Hebron
- Result: Pass (22 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/tool_execution/test_artifact_runtime_tool_execution.py backend/tests/agent_artifact_runtime/test_agent_artifact_runtime.py backend/tests/rag_artifact_runtime/test_rag_artifact_runtime.py backend/tests/platform_sdk_tool backend/tests/control_plane_sdk/test_client_and_modules.py`
- Date: 2026-03-11 18:18 EET
- Result: Pass (127 passed, 11 skipped)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_free_plan_runtime_worker.py`
- Date: 2026-03-12 01:58 Asia/Hebron
- Result: Pass (13 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-14 Asia/Hebron
- Result: Pass (5 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_artifact_versions_api.py backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/artifact_coding_agent/test_runtime_service.py backend/tests/platform_architect_workers/test_worker_runtime.py backend/tests/platform_architect_workers/test_architect_worker_integration.py backend/tests/control_plane_sdk/test_client_and_modules.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py`
- Date: 2026-03-16 19:41 EET
- Result: Pass (145 passed)
- Command: `python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_outbound_auth_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-24 Asia/Hebron
- Result: Pass (21 passed)

## Known Gaps

- no real Cloudflare deploy API integration coverage yet
- no migration script execution coverage yet
- no outbound worker end-to-end proxy coverage yet
- no deployed free-plan worker smoke test yet after wrapper changes
