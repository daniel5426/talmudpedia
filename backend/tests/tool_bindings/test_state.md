Last Updated: 2026-03-19

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
- deleting a `tool_impl` artifact deletes the bound tool row
- enabling a pipeline tool binding creates a draft `rag_pipeline` tool row
- pipeline-bound tool rows exposed through `/tools` now report explicit ownership/management metadata and registry action flags
- compiling a tool-enabled retrieval pipeline publishes the tool and pins `executable_pipeline_id`
- disabling and re-enabling a pipeline tool binding preserves custom schema overrides
- updating a published pipeline demotes the bound tool back to draft and clears the executable pin
- compiling an ingestion pipeline can also publish a `rag_pipeline` tool
- exporting an agent now creates an owner-managed `agent_call` tool row exposed through `/tools` as `agent_bound`
- publishing an exported agent syncs the bound tool to `PUBLISHED` and snapshots a tool version
- deleting an agent removes the exported bound tool row

## Last Run

- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/tool_bindings/test_agent_tool_bindings.py backend/tests/tools_guardrails/test_tools_api_guardrails.py backend/tests/tool_bindings/test_domain_owned_tool_bindings.py`
- Date: 2026-03-18 19:10 Asia/Hebron
- Result: pass (`14 passed`)

## Known Gaps / Follow-ups

- No frontend coverage yet for the pipeline-page tool settings panel or the registry redirect/open-editor actions.
- No dedicated migration-level assertions yet for legacy `rag_retrieval` rows upgrading to `rag_pipeline`.
