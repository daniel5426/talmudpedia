# Platform SDK Tool Tests

Last Updated: 2026-02-07

Scope:
- Platform SDK tool actions (`create_artifact_draft`, `promote_artifact`, `create_tool`, `run_agent`, `run_tests`).
- Plan validation for new action types.

Test files present:
- test_platform_sdk_actions.py
- test_platform_sdk_integration.py

Key scenarios covered:
- Plan validation accepts new draft/test actions and flags missing fields.
- `run_tests` evaluates `contains` and `jsonpath` assertions.
- Empty/non-action invocations (auth envelope and metadata probe) are ignored with `action=noop` instead of defaulting to `fetch_catalog`.
- Integration flow for artifact draft → promote → tool creation.
- Integration flow for `run_tests` via Platform SDK action.

Last run command: `pytest -q backend/tests/platform_sdk_tool/test_platform_sdk_actions.py`
Last run date: 2026-02-07
Last run result: pass (5 passed)

Known gaps / follow-ups:
- Add coverage for delegated workload token auth behavior on `/admin/artifacts` and `/tools` routes.
- Add assertions for `run_agent` slug resolution pagination edge cases.
