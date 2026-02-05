# Test State: Agent Builder Pipelines

Last Updated: 2026-02-04

**Scope**
Complex agent pipelines with Agent node tool binding and tool execution flow.

**Test Files**
- `test_agent_tool_binding.py`

**Scenarios Covered**
- Agent node executes configured tool from JSON tool call
- Tool output propagates to end node via `state.last_agent_output`

**Last Run**
- Command: `TEST_USE_REAL_DB=1 pytest backend/tests/agent_builder_pipelines/test_agent_tool_binding.py -vv`
- Date: 2026-02-04
- Result: Pass

**Known Gaps / Follow-ups**
- Tool name/slug resolution path
- Multi-tool or chained tool-call sequences
