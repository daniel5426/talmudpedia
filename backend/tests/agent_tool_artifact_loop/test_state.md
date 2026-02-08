# Test State: Agent Tool Artifact Loop (Reading Time)

Last Updated: 2026-02-06

**Scope**
Real DB seed and execution for an artifact-backed tool used inside the agent tool loop.

**Test Files**
- `test_artifact_tool_loop_seed.py`

**Scenarios Covered**
- Create a reading-time artifact tool and register it in the tool registry
- Create an agent that uses the tool in a tool loop (JSON fallback path)
- Execute the agent and confirm artifact tool output is persisted in run output

**Destructive Setup**
- Creates tenant-scoped tool and agent records
- Agent and tool are deleted unless `TEST_KEEP_AGENTS=1`

**Last Run**
- Command: Not run (new test)
- Date: 2026-02-06
- Result: Not run (not requested)

**Known Gaps / Follow-ups**
- Requires `TEST_USE_REAL_DB=1` and a valid chat model (see `TEST_CHAT_MODEL_SLUG`).
