# Test State: Agent Builder v3
Last Updated: 2026-03-31

**Scope**
Graph Spec 4.0 contract analysis, graph-analysis API coverage, canonical workflow modality toggles, legacy Start-contract migration, upstream-scoped ValueRef validation, typed Set State behavior, and End output materialization.

**Test Files**
- `test_graph_contract_v3.py`
- `test_graph_analysis_routes_v3.py`

**Scenarios Covered**
- Compiler metadata includes workflow input, state, node output, and node-scoped accessible-output inventories for Graph Spec 4.0
- Workflow input inventory exposes canonical public modalities (`text`, `files`, `audio`, `images`)
- Branching nodes normalize fresh branch configs to opaque `branch_*` ids
- Legacy `3.0` Start-owned state is normalized into top-level `state_contract`
- Agent node inventory uses the configured node label and only exposes the active output mode
- Graph analysis emits deduplicated template suggestions, with global workflow/state values and direct-input node outputs scoped per node
- Graph analysis route returns the normalized `4.0` analysis payload through the API surface
- Graph analysis route returns structured validation errors
- `set_state` must declare a type when creating a new state key under Graph Spec 4.0
- `set_state` writes typed `value_ref` assignments into workflow state
- `set_state` rejects compile-time `ValueRef` type mismatches
- Disabled workflow modalities are omitted from contract inventory and rejected by compile-time `ValueRef` validation
- non-upstream `node_output` references are rejected at compile time
- End output schema bindings materialize authoritative `final_output`
- assistant text extraction now prefers assistant-visible chat output over `final_output`
- string `final_output` remains available as a narrow text fallback when no assistant-visible chat output exists

**Last Run**
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/classify_executor/test_classify_executor.py backend/tests/agent_builder_v3/test_graph_contract_v3.py`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (`17 passed`)
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/agent_builder_v3/test_graph_contract_v3.py`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (`9 tests`)
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/agent_builder_v3/test_graph_contract_v3.py backend/tests/agent_builder_v3/test_graph_analysis_routes_v3.py backend/tests/tool_bindings/test_agent_tool_bindings.py backend/tests/tool_execution/test_agent_call_tool_execution.py`
- Date: 2026-03-31 Asia/Hebron
- Result: Pass (`19 tests`)
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/agent_builder_v3 backend/tests/agent_builder_nodes/test_speech_to_text_node.py backend/tests/node_inventory/test_node_contract_matrix.py backend/tests/agent_attachments backend/tests/model_accounting/test_run_invocation_service.py`
- Date: 2026-03-30 Asia/Hebron
- Result: Pass (`29 tests`)
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
