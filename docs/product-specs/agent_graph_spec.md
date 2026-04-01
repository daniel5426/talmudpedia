# Agent Graph Spec

Last Updated: 2026-04-01

This document is the canonical graph-definition contract for the agent builder, persistence layer, and backend compiler.

## Purpose

The agent graph spec is the persisted graph format shared by:
- agent builder frontend
- backend graph analysis and compilation
- agent save/update flows

## Draft-Legal Persistence

Agent graph persistence is draft-legal.

Rules:
- save/update must persist incomplete drafts
- publish does not certify runnability
- write-time rejection is reserved for illegal graph documents or illegal mutations
- compiler/runtime diagnostics remain explicit and advisory until execution

Examples of allowed draft state:
- disconnected nodes
- missing edges
- missing start/end nodes
- unreachable branches
- partially configured runnable nodes

Examples of rejected writes:
- graph payload is not an object
- graph payload fails schema parsing
- runtime config is stored in `data.config` instead of canonical `config`
- picker-backed references point to non-existent tenant/global resources

## Top-Level Contract

Persisted graph shape:

```json
{
  "spec_version": "4.0",
  "workflow_contract": {
    "inputs": []
  },
  "state_contract": {
    "variables": []
  },
  "nodes": [],
  "edges": []
}
```

`spec_version` may currently be omitted in legacy payloads, but persisted graphs should carry it explicitly.

## Current Supported Versions

- `1.0`
- `2.0`
- `3.0`
- `4.0`

Important current rule verified in code:
- if the graph contains GraphSpec v2 orchestration node types, the effective version must be `2.0`
- GraphSpec v2 orchestration is also feature-gated by tenant/surface checks in the backend compiler

Current builder/runtime direction:
- `4.0` is the active workflow/state contract format
- `3.0` is read-and-normalize legacy compatibility
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
- node config legality is enforced at edit/mutation time; incomplete config is allowed to persist

## Spec 4.0 Contract Additions

GraphSpec `4.0` adds:
- top-level `workflow_contract`
- top-level `state_contract`
- typed workflow/state inventory
- explicit node output contracts
- node-scoped template suggestion inventory for builder text/prompt inputs
- node-scoped value-ref source inventory for upstream-only binding
- structured value references for data-binding fields
- schema-driven `End`

## Start Node Contract

`Start` is no longer the canonical storage owner of workflow/state contracts in GraphSpec `4.0`.

For current chat workflows:
- `workflow_input.input_as_text: string` always exists as a built-in runtime variable
- `workflow_input.attachments: attachment[]` exposes serialized runtime attachment refs
- `workflow_input.audio_attachments: attachment[]` exposes the audio-only attachment subset
- `workflow_input.primary_audio_attachment: attachment` is exposed when at least one audio attachment exists
- `input_as_text` is compiler-generated and read-only
- persisted graph metadata stores workflow inputs and state definitions canonically
- `Start` remains the execution entry node and the UX projection point for editing those contracts

Persisted `state_contract.variables` entries:
- `key`
- `type`
- `default_value` optional

Persisted `workflow_contract.inputs` entries:
- `key`
- `type`
- `required`
- `label` optional
- `description` optional
- `semantic_type` optional
- `readonly` optional
- `derived` optional

## Runtime Namespaces

GraphSpec `4.0` standardizes runtime value lookup into:
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

Canonical GraphSpec `4.0` uses `ValueRef` for fields whose meaning is “select a runtime value source”.

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
- `speech_to_text`
  - `text`
  - `segments`
  - `language`
  - `attachments`
  - `provider_metadata`
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

Current STT node rules:
- `speech_to_text.config.source` is a required `ValueRef`
- `speech_to_text.config.model_id` is optional and falls back to the tenant/global default `speech_to_text` model
- multi-attachment STT joins transcript text with blank-line separators and publishes flattened segments with `attachment_id`

## Builder Suggestion Inventory

Graph analysis now exposes two different downstream contracts:
- raw typed inventory
  - `workflow_input`
  - `state`
  - `node_outputs`
  - `accessible_node_outputs_by_node`
- builder text/prompt suggestion inventory
  - `template_suggestions.global`
  - `template_suggestions.by_node`

Rules:
- `workflow_input` and `state` remain global
- `node_output` ValueRefs are valid only for reachable upstream nodes, never for self or unrelated nodes
- `accessible_node_outputs_by_node[nodeId]` is the canonical picker source for typed ValueRef UIs
- template suggestions are deduplicated and builder-facing
- global suggestions include workflow input and state
- `template_suggestions.by_node[nodeId]` includes only direct incoming node outputs for that node
- builder menus should render friendly labels while inserting one stable token per semantic value

## End Node Contract

GraphSpec `4.0` replaces legacy `End.output_variable` / `End.output_message` behavior with:
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
