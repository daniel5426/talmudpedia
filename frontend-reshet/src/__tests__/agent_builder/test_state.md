# Test State: Agent Builder (GraphSpec Serialization + Branch Handles)

Last Updated: 2026-02-05

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
- Date: 2026-02-05
- Result: Fail (branch handle test fails for `if_else` duplicate/blank names; graphspec test passes)

**Known Gaps / Follow-ups**
- No end-to-end builder save/publish UI test
