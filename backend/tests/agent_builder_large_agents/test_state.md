# Test State: Agent Builder Large Agents

Last Updated: 2026-02-05

**Scope**
Full-stack, multi-node agent graphs that mirror real UI flows (guardrails, classify, tools, RAG, approvals).

**Test Files**
- `test_large_agent_scenarios.py`

**Scenarios Covered**
- Customer support router with guardrail, classify, RAG + vector search, tool, and approval
- Query triage with rewrite, classify, RAG + vector search, tool, and deterministic routing
- Document compare flow with human input, RAG + vector search, tool, approval/rejection agents

**Destructive Setup**
- Purges all agents for the test tenant at the start of each test (user-approved).

**Last Run**
- Command: `TEST_USE_REAL_DB=1 TEST_KEEP_AGENTS=1 pytest -q backend/tests/agent_builder_large_agents/test_large_agent_scenarios.py`
- Date: 2026-02-05 18:18:59 +0200
- Result: Pass (agents preserved for manual UI inspection)

**Known Gaps / Follow-ups**
- Add UI-driven E2E coverage (Playwright) once builder UX stabilizes
