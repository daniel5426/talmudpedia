# Test State: Agent Builder (GraphSpec Serialization + Branch Handles)

Last Updated: 2026-03-06

**Scope**
Frontend GraphSpec v1 serialization, builder node normalization, and branch handle rendering.

**Test Files**
- `graphspec_serialization.test.tsx`
- `branch_handles.test.tsx`

**Scenarios Covered**
- GraphSpec v1 save writes canonical top-level `node.config` and strips persisted `data.config`
- Serialization of handle fields into GraphSpec v1
- Artifact input mappings normalization and preservation
- Classify and if/else branch handle IDs (fallbacks, dedupe, else handle)

**Last Run**
- Command: `npm test -- --runTestsByPath src/__tests__/agent_builder/graphspec_serialization.test.tsx`
- Date: 2026-03-06
- Result: Pass (1 suite, 2 tests)

**Known Gaps / Follow-ups**
- No end-to-end builder save/publish UI test
- GraphSpec v2 + runtime overlay coverage now lives in `../agent_builder_v2/`
