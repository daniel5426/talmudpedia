Last Updated: 2026-03-18

# Tool Bindings Test State

## Scope

Domain-owned tool bindings for `tool_impl` artifacts and visual pipelines.

## Test Files Present

- `test_domain_owned_tool_bindings.py`

## Key Scenarios Covered

- creating a `tool_impl` artifact auto-creates a draft bound tool row
- artifact-bound tool rows exposed through `/tools` now report explicit ownership/management metadata and registry action flags
- updating a `tool_impl` artifact resynchronizes the bound tool schema/config
- publishing a `tool_impl` artifact auto-publishes the bound tool and pins `artifact_revision_id`
- deleting a `tool_impl` artifact deletes the bound tool row
- enabling a pipeline tool binding creates a draft `rag_pipeline` tool row
- pipeline-bound tool rows exposed through `/tools` now report explicit ownership/management metadata and registry action flags
- compiling a tool-enabled retrieval pipeline publishes the tool and pins `executable_pipeline_id`
- disabling and re-enabling a pipeline tool binding preserves custom schema overrides
- updating a published pipeline demotes the bound tool back to draft and clears the executable pin
- compiling an ingestion pipeline can also publish a `rag_pipeline` tool

## Last Run

- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/builtin_tools_registry/test_builtin_registry_api.py backend/tests/tools_guardrails/test_tools_api_guardrails.py backend/tests/tool_bindings/test_domain_owned_tool_bindings.py`
- Date: 2026-03-18 16:00 Asia/Hebron
- Result: pass (`16 passed`)

## Known Gaps / Follow-ups

- No frontend coverage yet for the pipeline-page tool settings panel or the registry redirect/open-editor actions.
- No dedicated migration-level assertions yet for legacy `rag_retrieval` rows upgrading to `rag_pipeline`.
