# Test State: Agent Tool Agents

Last Updated: 2026-02-06

**Scope**
Full-stack, multi-node agent graphs that use only agent and tool nodes (plus start/end) to validate tool-loop behavior and tool-node handoffs.

**Test Files**
- `test_agent_tool_agents.py`

**Scenarios Covered**
- Support lookup agent using tool-loop calls followed by an audit tool node
- Multi-agent handoff that creates an action via a tool node and sends a notification via a second tool node

**Destructive Setup**
- Creates tenant-scoped tools for each test
- Agents and tools are deleted unless `TEST_KEEP_AGENTS=1`

**Last Run**
- Command: `TEST_USE_REAL_DB=1 TEST_KEEP_AGENTS=1 pytest -q /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_tool_agents/test_agent_tool_agents.py`
- Date: 2026-02-06 01:06:46 +0200
- Result: Pass (2 passed)

**Known Gaps / Follow-ups**
- Consider adding a deterministic tool-call test using a local provider stub if model compliance becomes flaky
