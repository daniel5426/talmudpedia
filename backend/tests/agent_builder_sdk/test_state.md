# Test State: Agent Builder SDK

Last Updated: 2026-04-22

**Scope**
SDK + HTTP integration for catalog parity, agent creation, execution, and validation helpers.

**Test Files**
- `test_sdk_http.py`

**Scenarios Covered**
- SDK catalog parity with `/agents/nodes/catalog`
- SDK create + execute agent via HTTP
- GraphSpecValidator catches invalid configs

**Last Run**
- Command: `TEST_USE_REAL_DB=1 TEST_BASE_URL=http://localhost:8000 pytest backend/tests/agent_builder_sdk -q`
- Date: 2026-02-04
- Result: Not run in this change

**Known Gaps / Follow-ups**
- Add SDK fuzzed-graph creation test once runtime limits are tuned

**Latest Relevant Run**
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/agent_builder_limits/test_limits.py backend/tests/agent_builder_sdk/test_sdk_http.py backend/tests/agent_builder_nodes/test_nodes_execute.py backend/tests/node_inventory/test_node_surface_inventory.py`
- Date: 2026-04-01 00:24 EEST
- Result: Pass (`15 passed, 5 skipped`; SDK HTTP cases skipped because local HTTP API was not running)
