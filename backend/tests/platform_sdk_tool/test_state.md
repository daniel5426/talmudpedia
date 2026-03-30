# Platform SDK Tool Tests

Last Updated: 2026-03-30

Scope:
- Platform SDK contract/parity behavior, explicit-action behavior, and strict canonical input enforcement.
- Domain-method action wrappers for control-plane SDK surfaces.
- Runtime primitive orchestration action dispatch and validation.
- This suite now covers the SDK/client-side parity layer only; architect runtime tool execution is tested separately in native `platform-*` runtime tests.

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
- Wrapped tool input in `value`/`query`/`text` is rejected with `NON_CANONICAL_PLATFORM_SDK_INPUT`.
- Unsupported invented RAG actions like `rag.nodes.catalog` return explicit structured `unknown_action` errors.
- Deprecated planner-centric actions (`validate_plan`, `execute_plan`) fail with explicit `deprecated_action` validation errors.
- Legacy artifact draft aliases are removed and now fail explicitly.
- Non-artifact architect-safety aliases still normalize to canonical domain action IDs where intentionally supported.
- Additional architect-safety aliases now map common non-canonical planner outputs to canonical IDs (e.g. `create_agent` -> `agents.create`) to prevent avoidable scope mismatch failures.
- `run_tests` evaluates `contains` and `jsonpath` assertions.
- Runtime primitive action dispatch routes through canonical orchestration action IDs.
- Action-to-SDK parity for `artifacts.create`, `artifacts.update`, `artifacts.convert_kind`, `artifacts.create_test_run`, `artifacts.delete`, `tools.create_or_update`, `tools.publish`, `agents.execute`, `agents.start_run`, `agents.get_run_tree`, `orchestration.spawn_run`, and `catalog.list_capabilities`.
- Action-to-SDK parity now also covers non-start-set canonical domains:
  - `rag.create_job`
  - `models.update_provider`
  - `credentials.delete`
  - `knowledge_stores.list`
- Additional matrix parity coverage now includes most remaining canonical dispatched actions across:
  - `catalog.*`, `rag.*`, `artifacts.*`, `tools.*`, `agents.*`, `models.*`, `credentials.*`, `knowledge_stores.*`, and `orchestration.*`.
- Canonical `agents.run_tests` action parity is covered explicitly (not only legacy alias path).
- Coverage markers include newly dispatched canonical architect/domain actions:
  - `rag.operators.catalog`
  - `rag.operators.schema`
  - `rag.list_visual_pipelines`
  - `rag.create_pipeline_shell`
  - `rag.create_visual_pipeline`
  - `rag.update_visual_pipeline`
  - `rag.graph.get`
  - `rag.graph.validate_patch`
  - `rag.graph.apply_patch`
  - `rag.graph.attach_knowledge_store_to_node`
  - `rag.graph.set_pipeline_node_config`
  - `rag.compile_visual_pipeline`
  - `rag.get_executable_pipeline`
  - `rag.get_executable_input_schema`
  - `agents.create_shell`
  - `agents.create`
  - `agents.update`
  - `agents.graph.get`
  - `agents.graph.validate_patch`
  - `agents.graph.apply_patch`
  - `agents.graph.add_tool_to_agent_node`
  - `agents.graph.remove_tool_from_agent_node`
  - `agents.graph.set_agent_model`
  - `agents.graph.set_agent_instructions`
- Agent node-intelligence action parity now covered:
  - `agents.nodes.catalog`
  - `agents.nodes.schema`
  - `agents.nodes.validate`
- Parity-coverage guard asserts every currently dispatched canonical action has a corresponding parity test reference.
- Cross-surface integration parity coverage now includes env-gated core mutation paths:
  - `artifacts.create`
  - `tools.create_or_update` (create)
  - `tools.create_or_update` (update)
  - `tools.publish`
  - `artifacts.publish`
  - `agents.create_or_update` (create)
  - `agents.publish`
  - `agents.start_run`
  - `agents.resume_run` (error-path parity on nonexistent run)
  These validate persisted-state equivalence across UI HTTP path, SDK path, and tool-action path.

Last run command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py`
Last run date/time: 2026-03-14 20:39 EET
Last run result: passed (`61 passed`)

Known gaps / follow-ups:
- Publish env-gated cross-surface parity runs into CI with controlled credentials to reduce skip-only coverage in default local runs.
