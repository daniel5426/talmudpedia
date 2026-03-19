# Built-in Tools Registry Tests

Last Updated: 2026-03-19

## Scope
Covers built-in catalog behavior plus ownership-aware `/tools` control-plane behavior for system rows and owner-managed bound rows.

## Test files present
- test_builtin_registry_api.py

## Key scenarios covered
- Global built-in catalog listing excludes tenant legacy built-in clone rows.
- Legacy built-in instance routes remain removed (`404`).
- Legacy tenant built-in clone rows can still be updated/deleted directly by ID for cleanup.
- `/tools` DTO now exposes canonical config fields (`implementation_config`, `execution_config`) and explicit ownership metadata for manual vs system rows.
- Manual and system tool creation paths now persist ownership/management metadata directly on `tool_registry`.
- Direct `/tools` creation of `rag_pipeline` rows is rejected because pipeline tools are domain-owned.
- Pipeline-bound rows reject registry-side update/publish and report managed ownership metadata through `/tools/{id}`.
- Owner-managed bound rows now use generic “owning domain” guardrail messaging.

## Last run command + result
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_api_guardrails.py backend/tests/tool_bindings/test_domain_owned_tool_bindings.py backend/tests/tool_bindings/test_agent_tool_bindings.py`
- Date/Time: 2026-03-18 19:13 Asia/Hebron
- Result: pass (`25 passed`)

## Known gaps or follow-ups
- Add disabled-flag coverage for built-in catalog endpoint (`BUILTIN_TOOLS_V1=0`).
