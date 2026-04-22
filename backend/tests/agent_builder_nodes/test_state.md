# Test State: Agent Builder Nodes

Last Updated: 2026-04-01

**Scope**
Node-by-node validation and execution for standard agent nodes (excluding tools and artifacts).

**Test Files**
- `test_nodes_execute.py`
- `test_speech_to_text_node.py`

**Scenarios Covered**
- Minimal and full configs for Agent nodes
- Execution for control, data, logic, reasoning, interaction, and retrieval nodes
- Node outputs stored in `_node_outputs`
- Legacy `conditional` and `human_input` are removed from the standard node surface
- `speech_to_text` resolves audio attachments from workflow input and emits the normalized transcript contract

**Last Run**
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/agent_builder_nodes/test_speech_to_text_node.py`
- Date: 2026-03-30 Asia/Hebron
- Result: Pass (`1 passed`)
- Command: `TEST_USE_REAL_DB=1 TEST_TENANT_EMAIL=danielbenassaya2626@gmail.com pytest backend/tests/agent_builder_graphs/test_graph_topologies.py::test_parallel_fanout_exec backend/tests/agent_builder_nodes/test_nodes_execute.py::test_parallel_execute backend/tests/agent_builder_nodes/test_nodes_execute.py::test_user_approval_execute -vv`
- Date: 2026-02-04
- Result: Pass (for `test_parallel_execute`, `test_user_approval_execute`)
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/agent_builder_limits/test_limits.py backend/tests/agent_builder_sdk/test_sdk_http.py backend/tests/agent_builder_nodes/test_nodes_execute.py backend/tests/node_inventory/test_node_surface_inventory.py`
- Date: 2026-04-01 00:24 EEST
- Result: Pass (`15 passed, 5 skipped`)

**Known Gaps / Follow-ups**
- Add richer semantic assertions for Agent output content if needed
