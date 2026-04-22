# Graph Authoring Tests

Last Updated: 2026-04-22

## Scope
- Backend-owned graph authoring normalization, schema-default application, and repair-grade validation for agent graphs and RAG pipelines.

## Test files present
- test_agent_authoring.py
- test_rag_authoring.py

## Key scenarios covered
- Agent write-path normalization applies backend schema defaults and canonical contract shaping before persistence.
- Agent validation returns path-specific authoring issues for unknown config fields and missing required fields.
- RAG graph normalization applies canonical operator defaults without frontend help.
- RAG authoring issues are path-specific and direct write-path normalization rejects unknown operators.

## Last run command + date/time + result
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/graph_authoring/test_agent_authoring.py backend/tests/graph_authoring/test_rag_authoring.py backend/tests/graph_mutation_agents/test_agent_graph_mutation_service.py backend/tests/graph_mutation_rag/test_rag_graph_mutation_service.py`
- Date/Time: 2026-04-22 Asia/Hebron
- Result: pass (`11 passed`)

## Known gaps or follow-ups
- Add DB-backed assertions for full create/update persistence flows once the surrounding legacy test drift is cleaned up.
