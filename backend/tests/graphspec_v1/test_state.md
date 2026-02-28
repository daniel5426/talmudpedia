# Test State: GraphSpec v1
Last Updated: 2026-03-01

**Scope**
GraphSpec v1 normalization and version validation behavior in the backend schema/validator.

**Test Files**
- `test_graphspec_v1.py`

**Scenarios Covered**
- Legacy field normalization: `inputMappings`, `sourceHandle`, `targetHandle`
- Unsupported `spec_version` validation error
- Routing handle normalization for whitespace in branch names

**Last Run**
- Command: `cd backend && TEST_USE_REAL_DB=0 pytest tests/graphspec_v1/test_graphspec_v1.py -q`
- Date: 2026-03-01
- Result: Pass (3 tests)

**Known Gaps / Follow-ups**
- No frontend serialization tests tracked here (see frontend test_state in agent_builder tests)
