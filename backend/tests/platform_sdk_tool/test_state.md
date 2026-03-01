# Platform SDK Tool Tests

Last Updated: 2026-03-01

Scope:
- Platform SDK tool action dispatch and strict explicit-action behavior.
- Domain-method action wrappers for control-plane SDK surfaces.
- Runtime primitive orchestration action dispatch and validation.

Test files present:
- test_platform_sdk_actions.py
- test_platform_sdk_integration.py
- test_platform_sdk_orchestration_actions.py
- test_platform_sdk_sdk_parity.py

Key scenarios covered:
- Missing action fails fast with structured validation errors (`MISSING_REQUIRED_FIELD`).
- Deprecated planner-centric actions (`validate_plan`, `execute_plan`) fail with explicit `deprecated_action` validation errors.
- Legacy action aliases normalize to canonical domain action IDs.
- `run_tests` evaluates `contains` and `jsonpath` assertions.
- Runtime primitive action dispatch routes through canonical orchestration action IDs.
- Action-to-SDK parity for `artifacts.create_or_update_draft`, `tools.create_or_update`, `agents.execute`, `orchestration.spawn_run`, and `catalog.list_capabilities`.

Last run command: `pytest -q backend/tests/platform_sdk_tool/test_platform_sdk_actions.py backend/tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py`
Last run date/time: 2026-03-01 18:28:32 EET
Last run result: pass (14 passed)

Known gaps / follow-ups:
- Expand parity coverage to additional canonical actions across all SDK modules.
- Add integration parity assertions comparing tool wrapper outputs with direct SDK HTTP calls on live env-gated runs.
