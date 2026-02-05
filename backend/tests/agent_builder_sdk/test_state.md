# Test State: Agent Builder SDK

Last Updated: 2026-02-04

**Scope**
SDK + HTTP integration for catalog parity, agent creation, execution, and validation helpers.

**Test Files**
- `test_sdk_http.py`

**Scenarios Covered**
- SDK catalog parity with `/agents/operators`
- SDK create + execute agent via HTTP
- GraphSpecValidator catches invalid configs

**Last Run**
- Command: `TEST_USE_REAL_DB=1 TEST_BASE_URL=http://localhost:8000 pytest backend/tests/agent_builder_sdk -q`
- Date: 2026-02-04
- Result: Not run in this change

**Known Gaps / Follow-ups**
- Add SDK fuzzed-graph creation test once runtime limits are tuned
