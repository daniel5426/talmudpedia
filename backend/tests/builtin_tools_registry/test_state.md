# Built-in Tools Registry Tests

Last Updated: 2026-02-15

## Scope
Covers built-in catalog behavior (no runtime template/instance semantics) and retrieval validation guardrails in the tools control-plane.

## Test files present
- test_builtin_registry_api.py

## Key scenarios covered
- Global built-in catalog listing excludes tenant legacy built-in clone rows.
- Legacy built-in instance routes remain removed (`404`).
- Legacy tenant built-in clone rows can still be updated/deleted directly by ID for cleanup.
- Regular `rag_retrieval` tool create/update reject cross-tenant retrieval pipeline IDs.
- Regular `rag_retrieval` publish validates tenant pipeline scope and creates a `ToolVersion` on success.

## Last run command + result
- Command: `pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py`
- Date/Time: 2026-02-15 (local)
- Result: pass (`7 passed`)

## Known gaps or follow-ups
- Add disabled-flag coverage for built-in catalog endpoint (`BUILTIN_TOOLS_V1=0`).
