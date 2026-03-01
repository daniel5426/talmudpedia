# Platform SDK Tool Tests

Last Updated: 2026-03-01

Scope:
- Platform SDK tool actions (`create_artifact_draft`, `promote_artifact`, `create_tool`, `run_agent`, `run_tests`).
- Plan validation for new action types.

Test files present:
- test_platform_sdk_actions.py
- test_platform_sdk_integration.py
- test_platform_sdk_orchestration_actions.py

Key scenarios covered:
- Plan validation accepts new draft/test actions and flags missing fields.
- Plan validation accepts orchestration runtime primitives (`spawn_run`, `spawn_group`, `join`, `cancel_subtree`, `evaluate_and_replan`, `query_tree`).
- `run_tests` evaluates `contains` and `jsonpath` assertions.
- Empty/non-action invocations now fail fast with structured validation errors (`MISSING_REQUIRED_FIELD`) when action is missing.
- Explicit action contract is enforced (no implicit infer-from-steps/tests/message action resolution).
- Deploy-agent step uses canonical `/agents` path only (no `/api/agents` fallback chain).
- Integration flow for artifact draft → promote → tool creation.
- Integration flow for `run_tests` via Platform SDK action.
- Runtime primitive action dispatch from `execute` routes to kernel-backed orchestration calls.

Last run command: `pytest -q backend/tests/platform_sdk_tool/test_platform_sdk_actions.py backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py`
Last run date/time: 2026-03-01 17:20:59 EET
Last run result: pass (11 passed)

Known gaps / follow-ups:
- Add coverage for delegated workload token auth behavior on `/admin/artifacts` and `/tools` routes.
- Add assertions for `run_agent` slug resolution pagination edge cases.
