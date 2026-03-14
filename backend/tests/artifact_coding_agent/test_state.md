# Artifact Coding Agent Tests

Last Updated: 2026-03-14

## Scope

Track backend coverage for the direct-use artifact coding agent wrapper, session state, and function tool pack.

## Test Files Present

- test_runtime_service.py

## Key Scenarios Covered

- create-mode session scoping via `draft_key`
- lightweight seed-based draft initialization builds a canonical initial snapshot without falling back to a generic `agent_node`
- relinking from `draft_key` to `artifact_id` without creating a second shared draft
- helper-tool/session state export returns canonical `artifact_create_payload` and `artifact_update_payload`
- saved artifact session hydration rebuilds the working snapshot from the canonical artifact row

## Last Run

- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/artifact_coding_agent/test_runtime_service.py`
- Date: 2026-03-14 20:39 EET
- Result: passed (`3 passed`)

## Known Gaps

- router prompt-run execution is still not covered in this feature directory
- no test yet asserts live artifact test-run reconciliation after a child run
