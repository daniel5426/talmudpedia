# Agent Graph Spec

Last Updated: 2026-03-29

This document is the canonical graph-definition contract for the agent builder and backend compiler.

## Purpose

The agent graph spec is the persisted graph format shared by:
- agent builder frontend
- backend graph validation and compilation
- agent save/update flows

## Top-Level Contract

Persisted graph shape:

```json
{
  "spec_version": "1.0",
  "nodes": [],
  "edges": []
}
```

`spec_version` may currently be omitted in legacy payloads, but persisted graphs should carry it explicitly.

## Current Supported Versions

- `1.0`
- `2.0`
- `3.0`

Important current rule verified in code:
- if the graph contains GraphSpec v2 orchestration node types, the effective version must be `2.0`
- GraphSpec v2 orchestration is also feature-gated by tenant/surface checks in the backend compiler

Current builder/runtime direction:
- `3.0` is the active workflow-contract format for the Start/End refactor
- `1.0` and `2.0` remain legacy compatibility shapes

## Node Contract

Required fields:
- `id`
- `type`
- `position`
- `config`

Optional fields:
- `label`
- `data`
- `input_mappings`

Current normalization behavior:
- `inputMappings` is normalized to `input_mappings`
- persisted functional config must live in `config`
- builder-only metadata can live in `data`, but `data.config` is not the source of truth

## Spec 3.0 Contract Additions

GraphSpec `3.0` adds:
- typed workflow/state inventory
- explicit node output contracts
- node-scoped template suggestion inventory for builder text/prompt inputs
- structured value references for data-binding fields
- schema-driven `End`

## Start Node Contract

`Start` is the workflow contract owner in GraphSpec `3.0`.

For current chat workflows:
- `workflow_input.input_as_text: string` always exists as a built-in runtime variable
- `input_as_text` is compiler-generated and read-only
- persisted `Start` config stores state definitions, not editable workflow input variables

Persisted `Start.config` shape:
- `state_variables`

`state_variables` entries:
- `key`
- `type`
- `default_value` optional

## Runtime Namespaces

GraphSpec `3.0` standardizes runtime value lookup into:
- `workflow_input`
- `state`
- `node_outputs`

Rules:
- `workflow_input` is immutable during a run
- `state` is mutable workflow-global state
- `node_outputs` is append-only per node execution result

## ValueRef Contract

Data-binding fields use a typed reference model instead of string interpolation as the primary contract.

`ValueRef` fields:
- `namespace`: `workflow_input | state | node_output`
- `key`
- `node_id` optional, required for `node_output`
- `expected_type` optional
- `label` optional, builder-facing only

Canonical GraphSpec `3.0` uses `ValueRef` for fields whose meaning is “select a runtime value source”.

## Node Output Contracts

Every runtime-producing node must declare a stable output contract. This inventory is the canonical downstream source for:
- builder pickers
- type checks
- `End` bindings
- runtime publication filtering
- builder template/prompt suggestion scoping

Current baseline output contracts:
- `start`
  - workflow input inventory only
- `agent`
  - `output_text` in text mode
  - `output_json` in structured-output mode
- `llm`
  - `output_text` in text mode
  - `output_json` in structured-output mode
- `tool`
  - `result`
- `rag`
  - `results`
  - `documents`
- `vector_search`
  - `results`
  - `documents`
- `classify`
  - `category`
  - `confidence` when available
- `transform`
  - `output`
- `human_input`
  - `input_text`
- `user_approval`
  - `approved`
  - `comment`
- artifact-backed nodes
  - output fields derived from artifact metadata

`set_state` is state-writing, not output-primary.

## Builder Suggestion Inventory

Graph analysis now exposes two different downstream contracts:
- raw typed inventory
  - `workflow_input`
  - `state`
  - `node_outputs`
- builder text/prompt suggestion inventory
  - `template_suggestions.global`
  - `template_suggestions.by_node`

Rules:
- the typed inventory remains graph-wide and is used by ValueRef pickers and validation
- template suggestions are deduplicated and builder-facing
- global suggestions include workflow input and state
- `template_suggestions.by_node[nodeId]` includes only direct incoming node outputs for that node
- builder menus should render friendly labels while inserting one stable token per semantic value

## End Node Contract

GraphSpec `3.0` replaces legacy `End.output_variable` / `End.output_message` behavior with:
- `output_schema`
- `output_bindings`

`output_schema` fields:
- `name`
- `mode`: `simple | advanced`
- `schema`: JSON Schema

`output_bindings` entries:
- `json_pointer`
- `value_ref`

Rules:
- `End` materializes the final workflow result from schema + bindings
- required schema properties must have bindings
- bindings are runtime references, not raw literals
- `End` is the authoritative source of `final_output`

## Execution Contract Boundary

When `End` exists, public execution surfaces should treat `final_output` as authoritative.

Implications:
- execution results must expose `final_output`
- persisted chat/thread surfaces may still expose `assistant_output_text` separately
- `assistant_output_text` and `final_output` are distinct internal concepts and must not be treated as implicit aliases
- “last assistant message” is not the canonical workflow result when `End` is present

## Edge Contract

Required fields:
- `id`
- `source`
- `target`

Optional fields:
- `type`
- `source_handle`
- `target_handle`
- `label`
- `condition`

Current normalization behavior:
- `sourceHandle` is normalized to `source_handle`
- `targetHandle` is normalized to `target_handle`

## Routing Handle Rules

Current routed/conditional handle patterns include:
- `if_else`: configured conditions plus `else`
- `classify`: configured categories
- `while`: `loop`, `exit`
- `user_approval`: routed handles validated by the compiler

## Current Builder Behavior

The frontend builder normalizes saved graphs by:
- stripping builder-only config duplication from `data`
- moving saved functional configuration into `config`
- serializing `input_mappings`
- serializing normalized edge handles
- resolving the effective `spec_version` based on whether orchestration-v2 nodes are present

## Canonical Implementation References

- `backend/app/agent/graph/schema.py`
- `backend/app/agent/graph/compiler.py`
- `backend/app/services/agent_service.py`
- `frontend-reshet/src/components/agent-builder/graphspec.ts`
