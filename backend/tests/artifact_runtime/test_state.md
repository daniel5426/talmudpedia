Last Updated: 2026-03-26

# Test State

## Scope

Artifact runtime revision, deploy, and dispatch-time credential lifecycle.

## Test Files Present

- `test_revision_service.py`
- `test_execution_service.py`
- `test_runtime_secret_service.py`
- `test_dependency_registry_service.py`
- `test_artifact_versions_api.py`
- `test_artifact_working_draft_api.py`

## Key Scenarios Covered

- create tenant artifact draft with source-tree runtime payload
- create tenant artifact draft without a user-authored slug
- update artifact and create a new draft revision
- reject language mutation after first artifact persistence
- allow neutral non-code files in artifact source trees while still enforcing that the active entry module matches the artifact language lane
- skip draft revision creation for no-op artifact saves
- publish the latest draft revision
- list saved artifact revisions through the admin API
- keep artifact version-list responses limited to list-item fields even when revisions carry detail-only metadata
- fetch one historical artifact revision snapshot through the admin API
- duplicate an artifact into a new tenant draft with Google Drive-style incremented names
- read and update the persisted artifact working-draft snapshot through the admin API
- keep saved-artifact working-draft persistence isolated from unrelated `draft_key`-scoped shared drafts
- reject wrapped legacy `tool_contract` payloads in saved artifact working drafts
- verify bundle builder hash stability
- verify build-hash stability across source-tree revisions
- verify Cloudflare package builder emits a runnable `main.py` worker entrypoint
- serialize free-plan worker module-load crashes as JSON detail payloads
- support package-style multi-file imports in the free-plan worker loader
- resolve Cloudflare deployment/dispatch flow for live runs
- create live artifact runs for `agent` and `rag` domains
- enforce published-only execution for live domains
- route background live runs to the configured queue class
- reconcile stale artifact test runs before applying tenant capacity
- default artifact test concurrency to 10 active runs per tenant
- validate exact string-literal `@{credential-id}` usage on save/publish/run
- rewrite deployed artifact source to `context.credentials[...]`
- inject resolved credential values only through run-time dispatch context
- reject disabled, missing, or non-scalar runtime credentials
- validate Python editor diagnostics for syntax errors and missing declared dependencies
- classify artifact imports into built-in, runtime-provided, declared, and declaration-required dependency rows
- distinguish platform-verified runtime-provided imports from broader Pyodide catalog imports
- verify Python package-name existence checks and invalid-name rejection before dependency add
- reject artifact handlers that do not implement the canonical three-argument contract
- reject test runs and publish attempts when the entry module does not define/export `execute(inputs, config, context)`
- send worker-for-platforms dispatch payloads without raw source uploads and without persisted secrets
- package Python dependencies through the official `pywrangler` deploy pipeline instead of custom vendoring
- package JS artifacts as Wrangler bundles with pinned compatibility metadata
- confirm current runtime reality: lightweight pywrangler-built workers run, but heavyweight SDK imports like `openai` are still an external deployed-runtime compatibility gap
- return a persisted failed test run instead of bubbling an eager dispatch crash as the only caller-visible failure
- promote nested dispatch-worker upstream detail into a visible root-cause payload for debugging
- pass artifact test-run input payloads through to the worker without wrapping them under `value`

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
- Command: `python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_runtime_secret_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-24 Asia/Hebron
- Result: Pass (21 passed)
- Command: `pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_runtime_secret_service.py`
- Date: 2026-03-24 Asia/Hebron
- Result: Pass (14 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_runtime_secret_service.py backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_free_plan_runtime_worker.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (29 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_runtime_secret_service.py backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_free_plan_runtime_worker.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (30 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_runtime_secret_service.py backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_free_plan_runtime_worker.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (32 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_dependency_registry_service.py backend/tests/artifact_runtime/test_runtime_secret_service.py backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_runtime/test_free_plan_runtime_worker.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (37 passed)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py`
- Date: 2026-03-25 12:46 EET
- Result: PASS (`7 passed, 1 warning`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (17 passed, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (34 passed, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_execution_service.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (14 passed, 1 warning)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_execution_service.py backend/tests/artifact_test_runs/test_artifact_test_run_api.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (21 passed, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_artifact_versions_api.py -k duplicate_artifact_creates_tenant_copy_with_incremented_name`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (1 passed, 1 deselected, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py -k 'neutral_files or entry_module_that_does_not_match_language_lane'`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (2 passed, 7 deselected, 1 warning)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_artifact_working_draft_api.py backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-25 17:07 EET
- Result: Pass (19 passed, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_artifact_working_draft_api.py`
- Date: 2026-03-25 Asia/Hebron
- Result: Pass (4 passed, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_artifact_versions_api.py -k excludes_detail_only_fields`
- Date: 2026-03-26 17:09 EET
- Result: Pass (1 passed, 2 deselected, 7 warnings)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_runtime/test_revision_service.py backend/tests/artifact_runtime/test_execution_service.py`
- Date: 2026-03-27 Asia/Hebron
- Result: Pass (`30 passed, 5 warnings`)

## Known Gaps

- no real Cloudflare deploy API integration coverage yet
- `test_artifact_versions_api.py` still contains an older publish-path test that currently requires Cloudflare deploy config in this local environment
- no migration script execution coverage yet
- no live deployed end-to-end `context.credentials` dispatch-injection smoke test in CI yet
- no automated guard yet to reject heavyweight but installable Python SDKs that still fail inside Cloudflare Python Workers at import time
