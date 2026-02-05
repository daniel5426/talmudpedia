# Test State: Compiler Routing

**Scope**
GraphIR compilation output, routing map generation, interrupt points, and routing validation errors.

**Test Files**
- `test_compiler_graphir_routing.py`

**Scenarios Covered**
- Routing map generation for `user_approval`
- Entry and exit node derivation
- Missing, duplicate, and invalid routing handle validation

**Last Run**
- Command: `TEST_USE_REAL_DB=0 pytest -q`
- Date: 2026-02-04 16:59 EET
- Result: Pass

**Known Gaps / Follow-ups**
- No explicit tests for `if_else`, `while`, or `classify` handle generation
