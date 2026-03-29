# Test State: Agent Builder v3
Last Updated: 2026-03-29

**Scope**
Graph Spec 3.0 contract analysis, graph-analysis API coverage, inventory validation, typed Set State behavior, and End output materialization.

**Test Files**
- `test_graph_contract_v3.py`
- `test_graph_analysis_routes_v3.py`

**Scenarios Covered**
- Compiler metadata includes workflow input, state, and node output inventories for Graph Spec 3.0
- Agent node inventory uses the configured node label and only exposes the active output mode
- Graph analysis emits deduplicated template suggestions, with global workflow/state values and direct-input node outputs scoped per node
- Graph analysis route returns the v3 analysis payload through the API surface
- Graph analysis route returns structured validation errors
- `set_state` must declare a type when creating a new state key under Graph Spec 3.0
- `set_state` writes typed `value_ref` assignments into workflow state
- `set_state` rejects compile-time `ValueRef` type mismatches
- End output schema bindings materialize authoritative `final_output`
- assistant text extraction now prefers assistant-visible chat output over `final_output`
- string `final_output` remains available as a narrow text fallback when no assistant-visible chat output exists

**Last Run**
- Command: `cd backend && pytest tests/agent_builder_v3/test_graph_contract_v3.py tests/agent_builder_v3/test_graph_analysis_routes_v3.py -q`
- Date: 2026-03-29 Asia/Hebron
- Result: Pass (9 tests)
- Command: `cd backend && pytest tests/agent_builder_v3/test_graph_contract_v3.py -q`
- Date: 2026-03-29 Asia/Hebron
- Result: Pass
- Command: `pytest -q backend/tests/agent_builder_v3`
- Date: 2026-03-22
- Result: Pass (8 tests)

**Known Gaps / Follow-ups**
- No route-level execution contract fixture yet for structured `final_output` responses
