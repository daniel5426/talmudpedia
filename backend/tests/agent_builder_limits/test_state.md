# Test State: Agent Builder Limits

Last Updated: 2026-02-04

**Scope**
Scale, stress, and fuzz testing for large graphs and concurrent executions.

**Test Files**
- `test_limits.py`

**Scenarios Covered**
- 50-node execution baseline
- 100-node compilation
- 200-node fuzzed graphs (gated by `TEST_STRESS=1`)
- Concurrency and dense-edge compile (gated by `TEST_STRESS=1`)

**Last Run**
- Command: `TEST_USE_REAL_DB=1 TEST_TENANT_EMAIL=danielbenassaya2626@gmail.com pytest backend/tests/agent_builder_graphs/test_graph_topologies.py::test_parallel_fanout_exec backend/tests/agent_builder_nodes/test_nodes_execute.py::test_parallel_execute backend/tests/agent_builder_limits/test_limits.py::test_50_node_execution backend/tests/agent_builder_limits/test_limits.py::test_invalid_model_fails backend/tests/agent_builder_nodes/test_nodes_execute.py::test_user_approval_and_human_input_execute -vv`
- Date: 2026-02-04
- Result: Pass (for `test_50_node_execution`, `test_invalid_model_fails`)

**Known Gaps / Follow-ups**
- Add explicit timeout enforcement assertions if runtime exposes them
