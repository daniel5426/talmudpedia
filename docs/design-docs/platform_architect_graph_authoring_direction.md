# Platform Architect Graph Authoring Direction

Last Updated: 2026-04-22

## Purpose

Capture the currently agreed direction for the `platform-architect` agent before node-by-node contract work begins.

The main goal of this agent is end-to-end creation of other agents, with RAG/tool integration when needed.

## Decision Summary

The long-term direction is:

- keep strong discovery/research tools for both agent nodes and RAG operators
- move toward canonical graph authoring as the main creation path
- make that graph authoring model-friendly by shifting boilerplate/defaulting into the backend
- defer toolset-loading optimization work until after the authoring contract is improved

This means the target architecture is not:

- four broad container tools with hidden sub-actions
- skills as the primary way to explain schema shape
- shell/helper-only authoring forever

The target architecture is:

- strong node/operator discovery
- canonical graph create/update contracts
- backend normalization/defaulting
- strict validation with useful repair signals

## Why

The current model-facing shape asks the agent to do too much hidden reasoning:

- choose the right domain container
- know which action exists under it
- know the input schema of that action
- shape `action + payload` correctly

That is a weak abstraction boundary for model use.

At the same time, fully generic graph authoring only works if the backend absorbs mechanical complexity. If the model has to author every low-level field itself, reliability drops again.

## Agreed Authoring Model

### 1. Discovery First

The architect should have strong research/read surfaces for:

- `agents.nodes.catalog`
- `agents.nodes.schema`
- `rag.operators.catalog`
- `rag.operators.schema`

These are the foundation for understanding what can be built.

### 2. Canonical Graph Authoring

The preferred long-term authoring path is full graph authoring, not container-tool indirection and not a large collection of special-case create helpers.

The model should author the meaningful structure:

- chosen nodes/operators
- important config choices
- graph connectivity
- high-level resource intent

The backend should own the mechanical parts:

- default values for omitted non-semantic fields
- normalization of accepted graph payloads
- generation of safe boilerplate when unambiguous
- strict structural validation

### 3. Backend Normalization

For this direction to work, graph creation/update must become easier for the model than it is today.

Expected backend responsibilities:

- fill default optional values
- reduce required boilerplate where safe
- keep canonical output shape stable
- return compiler-style validation errors with exact paths and missing fields

### 4. Validation And Repair

Raw graph authoring is only acceptable if the validation path is strong enough to support repair loops.

The backend should return errors that are:

- path-specific
- contract-specific
- easy for the model to repair without guessing

## What Is Deferred

The following is intentionally deferred for a later phase:

- dynamic toolset selection
- per-run toolset narrowing/expansion
- loading optimizations for large action inventories

Those remain important, but they are not the first pass.

## Immediate Working Assumption

For the next phase, the main effort should be:

1. improve node/operator research surfaces
2. improve graph authoring simplicity
3. add backend defaults/normalization where the model currently has to author boilerplate
4. tighten validation and repair signals
5. upgrade the contracts node by node / operator by operator

## Implementation Status

The first architect-facing hard cut has now landed in the backend:

- the architect no longer mounts the legacy `platform-rag`, `platform-agents`, `platform-assets`, or `platform-governance` container tools
- the architect now mounts `38` action-level platform tools plus `5` worker tools
- platform action tools are now real tool rows with direct-field schemas instead of `action + payload` container contracts
- the architect prompt is now graph-first and no longer teaches shell/helper authoring paths

The current implemented authoring surface is therefore:

- discovery via `agents.nodes.catalog`, `agents.nodes.schema`, `rag.operators.catalog`, `rag.operators.schema`
- graph-first creation/update via `agents.create`, `agents.update`, `rag.create_visual_pipeline`, `rag.update_visual_pipeline`
- repair checkpoints via `agents.validate` and `rag.compile_visual_pipeline`

The mounted architect surface is now explicitly runtime-scoped and project-owned:

- mounted architect tools do not ask the model for `organization_id` or `project_id`
- runtime control-plane context is authoritative for tenant/project scope
- the mounted asset surface now prefers explicit create/update actions where mixed contracts caused repair-loop failures, including:
  - `tools.create` / `tools.update`
  - `knowledge_stores.create` / `knowledge_stores.update`

The discovery surface is now richer on the schema side:

- `*.catalog` stays thin and is only for fast candidate selection
- `agents.nodes.schema` and `rag.operators.schema` now return:
  - full `config_schema` constraints
  - `input_schema` when there is a meaningful input contract
  - canonical `node_template`
  - omit-safe `normalization_defaults`
  - richer shared `instance_contract` details for the surrounding graph payload

This means the architect can now discover not only which nodes/operators exist, but also the minimal canonical node object it should author and which config defaults the backend will safely fill in.

The remaining deferred work is still deferred:

- toolset partitioning and dynamic loading
- broader public/MCP exposure strategy
- further node-by-node contract simplification on top of the new graph normalization work

## Debugging Principle

When evaluating `platform-architect` runs, do not assume every failure belongs to the architect tool surface itself.

Architect run failures can come from several different layers:

- architect behavior or repair policy
- action-tool contract design
- discovery/read-surface quality
- graph normalizers/defaulting
- node/operator authoring spec quality
- compiler/validator rules
- node/operator runtime implementation

The intended debugging approach is therefore:

1. inspect the exact tool call and error
2. identify the true failing layer
3. apply the fix at that layer instead of forcing a prompt-only workaround

This matters because the agreed direction is broader than “make the architect better at calling tools”.
As the architect is used to author graphs end to end, it is also a pressure test for:

- node/operator config contracts
- omit-safe defaults
- compiler semantics
- runtime behavior parity
- schema/discovery usefulness

So architect debugging is part of the node/operator polishing process, not a separate effort.

Recent examples from live runs already show this distinction:

- `query_input.text` being treated as compile-time required for retrieval graph authoring is a node/spec or validator issue, not primarily an architect tool issue
- `web_crawler.start_urls` behaving differently between compile-time config validation and runtime execution is a node contract/runtime parity issue, not primarily an architect tool issue
- repeated empty `rag.update_visual_pipeline` calls are architect repair-behavior issues

Those two node/operator issues have now been fixed in the current code:

- runtime-only RAG config fields no longer appear as authoring-required fields in discovery/catalog or authoring validation
- `web_crawler.start_urls` now accepts the same string-or-list contract in operator validation that the runtime executor already accepted

The fix policy should follow the real root cause:

- fix architect prompts/guardrails when the agent ignores a valid contract
- fix tool contracts when the model-facing schema is misleading
- fix node/operator specs, normalizers, or validators when the contract itself is wrong
- fix runtime node implementation when execution behavior disagrees with the published contract

## Non-Goals For This Doc

This document does not finalize:

- the exact future public MCP surface
- the exact final tool count for the architect
- the exact toolset-loading architecture

It only captures the agreed authoring direction that will guide the next implementation pass.
