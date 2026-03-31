# Test State: Node Surface Inventory

Last Updated: 2026-04-01

## Scope
- Generated inventory of the current agent-node and RAG-operator surfaces.
- Explicit drift reporting between agent graph schema enums and registered agent operators.

## Test files present
- test_node_contract_matrix.py
- test_node_surface_inventory.py

## Key scenarios covered
- Registered agent nodes report executor coverage.
- All registered agent nodes are iterable through the shared contract harness and expose stable contract-shape metadata.
- `speech_to_text` appears in the shared node contract matrix with the expected category and required config fields.
- All registered RAG operators are iterable through the shared contract harness and expose stable IO/config metadata.
- Schema-enum vs registry drift is explicit instead of implicit.
- Core RAG operator contract surfaces appear in the generated inventory.
- Generated Markdown includes the drift sections required for planning and coverage work.

## Last run command + date/time + result
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/agent_builder_limits/test_limits.py backend/tests/agent_builder_sdk/test_sdk_http.py backend/tests/agent_builder_nodes/test_nodes_execute.py backend/tests/node_inventory/test_node_surface_inventory.py`
- Date/Time: 2026-04-01 00:24 EEST
- Result: passed (`15 passed, 5 skipped`)
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/node_inventory/test_node_contract_matrix.py`
- Date/Time: 2026-03-30 Asia/Hebron
- Result: passed (`4 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/node_inventory`
- Date/Time: 2026-03-18 16:42 EET
- Result: passed (`8 passed, 5 warnings`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/test_env_bootstrap backend/tests/node_inventory backend/tests/builtin_tools_registry/test_builtin_registry_api.py`
- Date/Time: 2026-03-18 16:42 EET
- Result: passed (`23 passed, 6 warnings`)

## Known gaps or follow-ups
- Add regression coverage for tenant-scoped custom RAG operators once the first custom-operator inventory slice is in place.
