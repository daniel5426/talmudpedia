# Test State: GraphSpec v1

**Scope**
GraphSpec v1 normalization and version validation behavior in the backend schema/validator.

**Test Files**
- `test_graphspec_v1.py`

**Scenarios Covered**
- Legacy field normalization: `inputMappings`, `sourceHandle`, `targetHandle`
- Unsupported `spec_version` validation error

**Last Run**
- Command: `TEST_USE_REAL_DB=0 pytest -q`
- Date: 2026-02-04 16:59 EET
- Result: Pass

**Known Gaps / Follow-ups**
- No frontend serialization tests tracked here (see frontend test_state in agent_builder tests)
