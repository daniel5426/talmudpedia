# Test State: Agent Builder (GraphSpec Serialization + Branch Handles)

Last Updated: 2026-02-09

**Scope**
Frontend GraphSpec v1 serialization, builder node normalization, and branch handle rendering.

**Test Files**
- `graphspec_serialization.test.tsx`
- `branch_handles.test.tsx`

**Scenarios Covered**
- Serialization of legacy handle fields into GraphSpec v1
- Artifact input mappings normalization and preservation
- Classify and if/else branch handle IDs (fallbacks, dedupe, else handle)

**Last Run**
- Command: `npm test -- agent_builder`
- Date: 2026-02-09 18:42 EET
- Result: Pass (7 suites, 13 tests)

**Known Gaps / Follow-ups**
- No end-to-end builder save/publish UI test
- GraphSpec v2 + runtime overlay coverage now lives in `../agent_builder_v2/`
