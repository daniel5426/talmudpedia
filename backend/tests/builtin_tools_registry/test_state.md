# Built-in Tools Registry Tests

Last Updated: 2026-04-13

## Scope
Covers built-in catalog behavior plus ownership-aware `/tools` control-plane behavior for system rows and owner-managed bound rows.

## Test files present
- test_builtin_registry_api.py

## Key scenarios covered
- Global built-in catalog listing excludes tenant legacy built-in clone rows.
- Legacy built-in instance routes remain removed (`404`).
- Legacy tenant built-in clone rows can still be updated/deleted directly by ID for cleanup.
- `/tools` DTO now exposes canonical config fields (`implementation_config`, `execution_config`) and explicit ownership metadata for manual vs system rows.
- `/tools` now normalizes `execution.validation_mode` to `strict` by default on reads and writes.
- `/tools` built-in catalog now exposes `frontend_requirements` for frontend-dependent built-ins such as `ui_blocks`, including installer-based source ownership guidance.
- Manual and system tool creation paths now persist ownership/management metadata directly on `tool_registry`.
- Direct `/tools` creation of `rag_pipeline` rows is rejected because pipeline tools are domain-owned.
- Pipeline-bound rows reject registry-side update/publish and report managed ownership metadata through `/tools/{id}`.
- Owner-managed bound rows now use generic “owning domain” guardrail messaging.

## Last run command + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_api_guardrails.py backend/tests/tool_bindings/test_domain_owned_tool_bindings.py backend/tests/tool_bindings/test_agent_tool_bindings.py`
- Date/Time: 2026-03-19 14:36 EET
- Result: pass (`22 passed`)
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia/backend python3 -m pytest -q /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/builtin_tools_registry/test_builtin_registry_api.py /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/published_apps/test_builder_agent_integration_contract.py /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/builtin_tool_execution/test_builtin_tool_executor.py`
- Date/Time: 2026-03-30
- Result: pass (`28 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_api_guardrails.py backend/tests/tools_guardrails/test_tool_tenant_scoping.py backend/tests/published_apps/test_builder_agent_integration_contract.py::test_builder_agent_contract_includes_ui_blocks_frontend_requirements`
- Date/Time: 2026-04-13 Asia/Hebron
- Result: PASS (`22 passed, 9 warnings`)

## Known gaps or follow-ups
- Add disabled-flag coverage for built-in catalog endpoint (`BUILTIN_TOOLS_V1=0`).
