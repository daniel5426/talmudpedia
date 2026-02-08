# Agent Tool Agents Tests: What Was Added and Why

Last Updated: 2026-02-05

## Purpose
Add full-stack, real-DB test coverage for **agent graphs composed only of agents and tools** (plus start/end), with emphasis on the new tool-loop behavior and multi-agent tool handoffs. These tests are intended to validate that the runtime can execute realistic, tool-driven agent flows end-to-end and that created agents remain visible for manual inspection when desired.

## Test Taxonomy (High-Level)

### Backend Full-Stack Agent + Tool Tests (Pytest + Real DB)
**Location**: `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_tool_agents/test_agent_tool_agents.py`

**Why**: The LangChain tool-loop update introduced new execution semantics for agent tool calls. We needed full-stack tests that run **real agents and real tools** to validate production-like flows (not just unit tests of the loop).

**How**:
- Create tenant-scoped tools per test (internal implementation, execution metadata set).
- Build graphs using only `agent` and `tool` nodes (plus start/end).
- Execute via `AgentService` against the real DB.
- Assert node outputs contain tool execution records.

**Scenarios Included**:
- **Support lookup tool loop**: Agent uses tool-loop JSON fallback to call a lookup tool, then a tool node writes an audit log.
- **Multi-agent tool handoff**: One agent drafts an action payload for a tool node, another agent crafts a notification payload for a second tool node.

**Type**: Full-stack integration tests (real DB + model provider). These may be flaky if the model fails to follow strict JSON/tool instructions.

## Execution Behavior & Controls
- Agents/tools are **preserved** when `TEST_KEEP_AGENTS=1` (so you can inspect them in the UI).
- Real DB required: `TEST_USE_REAL_DB=1`.

## Related Test State Files
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/agent_tool_agents/test_state.md`
