# Platform SDK Tool Tests

Last Updated: 2026-03-01

Scope:
- Platform SDK tool action dispatch and strict explicit-action behavior.
- Domain-method action wrappers for control-plane SDK surfaces.
- Runtime primitive orchestration action dispatch and validation.

Test files present:
- test_platform_sdk_actions.py
- test_platform_sdk_integration.py
- test_platform_sdk_cross_surface_parity_integration.py
- test_platform_sdk_cross_surface_parity_execution_integration.py
- test_platform_sdk_orchestration_actions.py
- test_platform_sdk_sdk_parity.py
- test_platform_sdk_sdk_parity_additional_actions.py

Key scenarios covered:
- Missing action fails fast with structured validation errors (`MISSING_REQUIRED_FIELD`).
- Deprecated planner-centric actions (`validate_plan`, `execute_plan`) fail with explicit `deprecated_action` validation errors.
- Legacy action aliases normalize to canonical domain action IDs.
- `run_tests` evaluates `contains` and `jsonpath` assertions.
- Runtime primitive action dispatch routes through canonical orchestration action IDs.
- Action-to-SDK parity for `artifacts.create_or_update_draft`, `artifacts.delete`, `tools.create_or_update`, `tools.publish`, `agents.execute`, `agents.start_run`, `agents.get_run_tree`, `orchestration.spawn_run`, and `catalog.list_capabilities`.
- Action-to-SDK parity now also covers non-start-set canonical domains:
  - `rag.create_job`
  - `models.update_provider`
  - `credentials.delete`
  - `knowledge_stores.list`
  - `auth.mint_workload_token`
  - `workload_security.decide_approval`
- Additional matrix parity coverage now includes most remaining canonical dispatched actions across:
  - `catalog.*`, `rag.*`, `artifacts.*`, `tools.*`, `agents.*`, `models.*`, `credentials.*`, `knowledge_stores.*`, `auth.*`, `workload_security.*`, and `orchestration.*`.
- Canonical `agents.run_tests` action parity is covered explicitly (not only legacy alias path).
- Parity-coverage guard asserts every currently dispatched canonical action has a corresponding parity test reference.
- Cross-surface integration parity coverage now includes env-gated core mutation paths:
  - `artifacts.create_draft`
  - `tools.create_or_update` (create)
  - `tools.create_or_update` (update)
  - `tools.publish`
  - `artifacts.promote`
  - `agents.create_or_update` (create)
  - `agents.publish`
  - `agents.start_run`
  - `agents.resume_run` (error-path parity on nonexistent run)
  These validate persisted-state equivalence across UI HTTP path, SDK path, and tool-action path.

Last run command: `cd backend && pytest tests/platform_sdk_tool/test_platform_sdk_cross_surface_parity_integration.py tests/platform_sdk_tool/test_platform_sdk_cross_surface_parity_execution_integration.py tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py tests/platform_sdk_tool/test_platform_sdk_actions.py tests/platform_sdk_tool/test_platform_sdk_orchestration_actions.py tests/control_plane_sdk/test_no_legacy_api_agents_refs.py`
Last run date/time: 2026-03-01 21:02:14 EET
Last run result: pass (74 passed, 9 skipped)

Known gaps / follow-ups:
- Promote env-gated cross-surface parity runs into CI with controlled credentials to reduce skip-only coverage in default local runs.
