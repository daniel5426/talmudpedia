# RAG Graph Mutation Tests

Last Updated: 2026-04-22

## Scope
- Safe graph mutation primitives and RAG-operator config-path validation.
- Apply-path legality checks with advisory diagnostics after persistence.

## Test files present
- test_rag_graph_mutation_service.py
- test_rag_graph_mutation_routes.py

## Key scenarios covered
- Generic graph operations patch pipeline-node config without rebuilding edges.
- Unknown RAG config fields are rejected by schema-aware path validation.
- Incomplete pipeline drafts still persist through `RagGraphMutationService.apply_patch`.
- Backend graph-authoring normalization now runs before RAG patch preview/persist, and patch validation can include canonical authoring issues such as missing required config alongside compiler diagnostics.
- Route-level failures return structured HTTP errors with `request_id`, operation name, and mutation phase.
- RAG graph mutation batch is green alongside architect-runtime and SDK parity RAG authoring coverage.

## Last run command + date/time + result
- Command: `pytest -q backend/tests/graph_mutation_agents/test_agent_graph_mutation_service.py backend/tests/graph_mutation_rag/test_rag_graph_mutation_service.py backend/tests/agent_graph_validation/test_agent_graph_validation.py backend/tests/rag_execution_state/test_stale_executable_state.py`
- Date/Time: 2026-04-01
- Result: pass (`22 passed` across the targeted draft-legal backend suites)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/graph_mutation_rag/test_rag_graph_mutation_service.py backend/tests/graph_mutation_rag/test_rag_graph_mutation_routes.py backend/tests/platform_architect_runtime/test_platform_architect_runtime.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py backend/tests/control_plane_sdk/test_http_integration.py -k 'rag or pipeline or operators or compile_visual_pipeline or create_pipeline_shell or attach_knowledge_store_to_node or set_pipeline_node_config or executable'`
- Date/Time: 2026-04-14 Asia/Hebron
- Result: pass (`29 passed, 62 deselected, 8 warnings`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/graph_authoring/test_agent_authoring.py backend/tests/graph_authoring/test_rag_authoring.py backend/tests/graph_mutation_agents/test_agent_graph_mutation_service.py backend/tests/graph_mutation_rag/test_rag_graph_mutation_service.py`
- Date/Time: 2026-04-22 Asia/Hebron
- Result: pass (`11 passed`)

## Known gaps or follow-ups
- Add DB-backed API tests for the new `/admin/pipelines/visual-pipelines/{pipeline_id}/graph/*` routes.
