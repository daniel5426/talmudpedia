# Test State: Agent Builder Nodes

Last Updated: 2026-02-04

**Scope**
Node-by-node validation and execution for standard agent nodes (excluding tools and artifacts).

**Test Files**
- `test_nodes_execute.py`

**Scenarios Covered**
- Minimal and full configs for LLM/Agent nodes
- Execution for control, data, logic, reasoning, interaction, and retrieval nodes
- Node outputs stored in `_node_outputs`

**Last Run**
- Command: `TEST_USE_REAL_DB=1 TEST_TENANT_EMAIL=danielbenassaya2626@gmail.com pytest backend/tests/agent_builder_graphs/test_graph_topologies.py::test_parallel_fanout_exec backend/tests/agent_builder_nodes/test_nodes_execute.py::test_parallel_execute backend/tests/agent_builder_nodes/test_nodes_execute.py::test_user_approval_and_human_input_execute -vv`
- Date: 2026-02-04
- Result: Pass (for `test_parallel_execute`, `test_user_approval_and_human_input_execute`)

**Known Gaps / Follow-ups**
- Add richer semantic assertions for LLM output content if needed
