Last Updated: 2026-04-21

# Tool Bindings Test State

## Scope

Domain-owned tool bindings for `tool_impl` artifacts, visual pipelines, and exported agents.

## Test Files Present

- `test_domain_owned_tool_bindings.py`
- `test_agent_tool_bindings.py`

## Key Scenarios Covered

- creating a `tool_impl` artifact auto-creates a draft bound tool row
- artifact-bound tool rows exposed through `/tools` now report explicit ownership/management metadata and registry action flags
- artifact, pipeline, and agent export flows now persist ownership/source metadata directly on the bound `tool_registry` rows
- updating a `tool_impl` artifact resynchronizes the bound tool schema/config
- publishing a `tool_impl` artifact auto-publishes the bound tool and pins `artifact_revision_id`
- publishing a non-`tool_impl` artifact does not create or publish an artifact-bound tool row
- draft edits to a published `tool_impl` artifact leave the bound tool pinned to the last published revision until the next artifact publish
- deleting a `tool_impl` artifact deletes the bound tool row
- enabling a pipeline tool binding creates a draft `rag_pipeline` tool row
- pipeline bindings can now set a model-facing tool name while keeping the slug pipeline-derived
- pipeline-bound tool rows exposed through `/tools` now report explicit ownership/management metadata and registry action flags
- compiling a tool-enabled retrieval pipeline publishes the tool and pins `executable_pipeline_id`
- disabling and re-enabling a pipeline tool binding preserves custom schema overrides
- updating a published pipeline demotes the bound tool back to draft and clears the executable pin
- compiling an ingestion pipeline can also publish a `rag_pipeline` tool
- exporting an agent now creates an owner-managed `agent_call` tool row exposed through `/tools` as `agent_bound`
- exported agent tools now inherit the source agent `project_id`, and export routes resolve the source agent inside the active project
- exported agent-tool input schemas are now generated from built-in workflow modalities plus declared state vars instead of an export-time custom schema
- publishing an exported agent syncs the bound tool to `PUBLISHED` and snapshots a tool version
- deleting an agent removes the exported bound tool row

## Last Run

- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_api_guardrails.py backend/tests/tool_bindings/test_domain_owned_tool_bindings.py backend/tests/tool_bindings/test_agent_tool_bindings.py`
- Date: 2026-03-19 14:36 EET
- Result: pass (`22 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/tool_bindings/test_domain_owned_tool_bindings.py backend/tests/tool_bindings/test_agent_tool_bindings.py`
- Date: 2026-03-26 Asia/Hebron
- Result: pass (`6 passed`)
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/tool_bindings/test_domain_owned_tool_bindings.py`
- Date: 2026-03-30 Asia/Hebron
- Result: pass (`4 passed`)
- Command: `PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia python3 -m pytest -q backend/tests/tool_bindings/test_agent_tool_bindings.py`
- Date: 2026-03-31 Asia/Hebron
- Result: pass (`3 passed`)
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia backend/.venv/bin/python -m pytest -q backend/tests/tool_bindings/test_agent_tool_bindings.py`
- Date: 2026-04-21 Asia/Hebron
- Result: pass (`3 passed`). Agent-export lookup now follows source-object metadata instead of the old derived slug convention.
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/tool_bindings/test_agent_tool_bindings.py`
- Date: 2026-04-21 Asia/Hebron
- Result: pass (`3 passed`). Agent export/publish/delete flows remain green after project-scoping the source agent lookup and bound-tool rows.
- Command: `SECRET_KEY=explicit-test-secret PYTHONPATH=/Users/danielbenassaya/Code/personal/talmudpedia backend/.venv/bin/python -m pytest -q backend/tests/tool_bindings/test_domain_owned_tool_bindings.py -x`
- Date: 2026-04-21 Asia/Hebron
- Result: fail on first test. Local artifact creation currently errors with `invalid input value for enum artifactownertype: "organization"` before the tool-binding assertions run.

## Known Gaps / Follow-ups

- No dedicated migration-level assertions yet for legacy `rag_retrieval` rows upgrading to `rag_pipeline`.
- Local DB enum drift currently blocks `test_domain_owned_tool_bindings.py` artifact-route coverage (`artifactownertype` rejects `"organization"`).
