# Test State: GraphSpec v1
Last Updated: 2026-03-22

**Scope**
Legacy GraphSpec normalization and backend version validation behavior.

**Test Files**
- `test_graphspec_v1.py`

**Scenarios Covered**
- Legacy field normalization: `inputMappings`, `sourceHandle`, `targetHandle`
- Graph Spec `3.0` acceptance plus unsupported version rejection
- Routing handle normalization for whitespace in branch names

**Last Run**
- Command: `pytest -q backend/tests/graphspec_v1/test_graphspec_v1.py`
- Date: 2026-03-22
- Result: Pass (3 tests)

**Known Gaps / Follow-ups**
- No frontend serialization tests tracked here (see frontend test_state in agent_builder tests)
