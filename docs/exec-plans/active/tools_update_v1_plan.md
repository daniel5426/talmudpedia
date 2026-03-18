# Execution Plan: Tools Update V1

Last Updated: 2026-03-18

## Status: In Progress

This plan tracks the first slice of the tools rework.

## Current Slice Progress

Implemented in the current pass:
- `/tools` DTOs now expose explicit derived config fields:
  - `implementation_config`
  - `execution_config`
- `/tools` DTOs now expose explicit ownership/management metadata:
  - `ownership`
  - `managed_by`
  - `source_object_type`
  - `source_object_id`
  - `can_edit_in_registry`
  - `can_publish_in_registry`
  - `can_delete_in_registry`
- frontend tools UI now consumes those fields directly instead of reconstructing meaning from `config_schema`
- dead frontend `/tools/{id}/test` client code has been removed
- regression coverage now explicitly checks:
  - manual vs system DTO metadata
  - artifact-bound and pipeline-bound managed metadata
  - direct `/tools` creation rejection for domain-owned types

Still pending inside V1:
- persistence-level ownership metadata is not yet first-class in the DB model; current ownership metadata is derived at the API layer
- broader UX reframing of tool creation around user intent remains for a later slice

## Slice 1: Ownership Clarification

The current tools system has an ownership ambiguity.

At the documentation level, the tools domain is described as a DB-backed registry centered on `/tools`, including artifact-backed tools. At the implementation level, that is only partially true.

There are currently two different ownership models mixed together:

1. Manual tools
- These are truly owned by the tools domain.
- They are created, updated, versioned, and published through `/tools`.

2. Domain-owned bound tools
- `artifact` tools are owned by `tool_impl` artifacts.
- `rag_pipeline` tools are owned by visual/executable pipelines.
- Their lifecycle is not actually managed from `/tools`.
- Instead, their tool rows are created and synchronized by the binding layer.

In practice, `ToolRegistry` is serving two roles at once:
- the runtime-facing callable catalog used by agents
- the authoring source of truth for only some tool types

That mismatch creates confusion in docs, backend behavior, and frontend UX:
- the spec implies `/tools` is the authoring surface for all tools
- the backend rejects normal `/tools` authoring flows for artifact and pipeline tools
- the frontend presents one registry, but some rows are read-only because they belong to another domain

## Proposed Direction For This Slice

We should make ownership explicit instead of implicit.

Target model:

1. Manual tools
- Owned by the tools domain
- Managed in `/tools`

2. Artifact-bound tools
- Owned by artifact authoring
- Mirrored into `ToolRegistry` for runtime selection

3. Pipeline-bound tools
- Owned by pipeline authoring
- Mirrored into `ToolRegistry` for runtime selection

4. System tools
- Owned by backend seeding/runtime code
- Exposed through the same runtime catalog

Under this model, `ToolRegistry` remains the unified agent-facing catalog, but not every row is authored there.

## Why This Slice Comes First

This ownership clarification should come before broader tools cleanup because it determines:
- which API surface is authoritative for each tool type
- which UI surfaces are editable versus read-only
- where publish/version lifecycle belongs
- how docs should describe the tools domain

Without this cut, later cleanup will keep mixing registry concerns with owning-domain concerns.

## Immediate Follow-Up For Later Slices

- add explicit ownership metadata to tool DTOs and persistence
- align the docs with the actual ownership model
- make the tools UI show managed/read-only rows clearly
- keep `/tools` CRUD limited to manual tools
- keep artifact/pipeline publish flows in their owning domains

## Severity-Ordered Gaps

1. Ownership model is ambiguous
- `ToolRegistry` currently looks like one tools domain, but artifact tools and pipeline tools are actually domain-owned bindings rather than normal `/tools`-owned tools.
- This affects docs, API authority, publish flow, and UI editing rules.

2. Frontend/backend tools contract drift
- The frontend and backend do not expose one clean canonical tool DTO.
- The frontend still treats `implementation_config` and `execution_config` as first-class fields, while the backend actually returns `config_schema`.
- There is also a dead frontend `/tools/{id}/test` client path with no backend route.

3. Function tools are not a clean single source of truth
- A `FUNCTION` tool row exists in `ToolRegistry`, but execution depends on a process-local callable registry plus import side effects.
- Seeded system tools make this especially visible, but the underlying coupling exists across function-tool execution.

4. Tool contract strictness is inconsistent
- Some tools are strict and schema-driven.
- Others still rely on broad input coercion, wrapper flattening, and string-to-JSON recovery.
- This improves resilience but weakens contract clarity and predictability.

5. Tool taxonomy and naming drift
- Docs and legacy language still mention `rag_retrieval` while the implementation has largely standardized on `rag_pipeline`.
- This creates avoidable confusion in specs, tests, and UI language.

6. Bound-tool metadata is duplicated
- Artifact-bound tool rows carry schema/config that is also present in artifact `tool_contract`.
- The system works, but canonical precedence is not explicit enough.

7. Built-in/system/manual categories are not explicit enough
- Current grouping is mostly API-derived (`built_in`, `mcp`, `artifact`, `custom`) rather than true ownership/management modeling.

8. MCP governance is still thin
- The MCP runtime path works, but stronger host/policy/circuit-breaker controls are still missing.

## Staged Roadmap

### V1: Ownership And Contract Cut

This phase should remove the biggest structural ambiguity and make the tools surface explainable.

1. Make ownership explicit
- Introduce a clear ownership model for:
  - manual tools
  - artifact-bound tools
  - pipeline-bound tools
  - system tools
- Keep `ToolRegistry` as the unified runtime-facing catalog.
- Stop treating every row as if it shares the same authoring surface.

2. Align docs with actual ownership
- Update tools docs so artifact and pipeline tools are described as domain-owned bindings.
- Remove wording that implies `/tools` is the authoring surface for all tool types.

3. Define a canonical tool DTO
- Standardize what the frontend consumes.
- Make derived fields explicit instead of forcing UI code to reconstruct meaning from `config_schema`.
- Include ownership/management metadata so the UI can clearly show editable vs managed rows.

4. Clean up dead or drifting API/UI contracts
- Either implement `/tools/{id}/test` or remove the dead client path.
- Align frontend types with backend responses.

5. Reframe tool creation UX around user intent
- The top-level creation UX should follow what users are actually trying to do:
  - expose agent/workflow as tool
  - expose artifact as tool
  - expose RAG pipeline as tool
  - create integration tool
- The generic tools registry modal should be reserved for integration-style/manual tools.

## Domain-Native Tool Creation: Current State And Direction

### Artifacts

Artifacts are already the closest domain to the target model.

Current implementation:
- `tool_impl` artifacts are effectively native tools.
- creating or updating an artifact synchronizes a bound tool row automatically
- publishing an artifact publishes the bound tool automatically and pins `artifact_revision_id`

Implication:
- artifacts do not need a separate “export as tool” flow
- the artifact page is already the native authoring surface
- if an artifact is `tool_impl`, it should be treated as a tool-first artifact

Current limitation:
- the model-facing tool metadata is still mirrored through the bound tool row, so docs and UI should make that relationship clearer

### RAG Pipelines

Pipelines already have a partial domain-native export model.

Current implementation:
- there is a dedicated pipeline tool-binding API
- users can enable/disable tool exposure for a pipeline
- users can currently edit:
  - tool description
  - tool input schema
- compiling/publishing the pipeline publishes the bound tool and pins `executable_pipeline_id`

Implication:
- this is already an export/binding flow from the pipeline domain
- it should remain owned by the pipeline surface rather than being redirected into generic `/tools` CRUD

Current limitation:
- the current binding model does not let the user set a separate model-facing tool name
- tool name and slug are still derived from the pipeline identity

Direction:
- extend the pipeline binding flow so users can set model-facing tool metadata cleanly, starting with:
  - name
  - description
  - input schema

### Agents / Workflows

Agents do not currently have an equivalent export-to-tool model.

Current implementation:
- agents can reference tools
- agent builder attaches tools to an agent node through a flat `tools` list
- agents store tool references as lists of ids/slugs

Implication:
- “turn agent/workflow into a tool” is not implemented today
- this will require a new backend export/binding path rather than just a UI button

Direction:
- add a domain-native “export as tool” flow for agents/workflows
- that flow should create a tool/binding result using the existing tool model, with editable model-facing metadata:
  - name
  - description
  - input schema

### Unified Conversion Flow

We do not currently need a separate persisted conversion model.

Instead:
- the existing tool model should remain the persisted result
- “conversion” should be treated as a unified UI/backend flow that creates or updates that tool record/binding from another domain object

Shared user-editable fields across domain-native export flows:
- tool name
- tool description
- tool input schema

Default behavior:
- start from the source object’s current name/description/derived schema
- let the user edit those fields so they become model-facing tool metadata rather than a raw copy of the source object

## Agent Tool UX And Binding Model

### Current State

The current agent tool UX is still too thin for the target experience.

Current implementation:
- the agent builder loads published tools only
- the agent node stores selected tools as a flat list of tool ids
- the UI presents selected tools as badges plus a picker

Current limitation:
- there is no per-agent tool binding object
- there is no place for agent-specific tool overrides
- there is no embedded agent-node tool visualization beyond the simple picker/badge flow

### Target UX Direction

The target agent UX should be:
- the main agent node grows to visually contain its tools
- attached tools appear as small blocks/chips inside the main agent block
- selecting a tool block opens the right floating settings panel
- that panel edits the agent-tool binding, not the canonical global tool definition

### Required Data-Model Direction

The current flat `tools: []` model is not sufficient for this UX.

To support per-agent configuration, we need a richer binding model so an agent can hold:
- tool reference
- enabled state
- per-agent config override
- possibly policy/instruction overrides later

That is especially important for reusable tools like web search, where different agents may need different settings.

### V2: Function Tool Runtime Cleanup

This phase should make backend-native tool execution explicit and reduce hidden coupling.

1. Define the intended role of `FUNCTION` tools
- Treat them primarily as backend-native/internal capabilities.
- Avoid presenting them as a user-authored executable tool model.

2. Replace import-side-effect registration with explicit registration
- Move toward explicit runtime bootstrap for function-tool callables.
- Reduce dependence on “module happened to be imported” behavior.

3. Unify function-tool specs and seeded rows
- Drive runtime callable registration and seeded tool creation from one explicit source.
- Make the relationship between callable implementation and registry row deterministic.

4. Clarify user-facing creation policy
- Decide whether tenant users should create `FUNCTION` tools at all, or whether they should primarily create `ARTIFACT` tools.

### V3: Contract Tightening And Taxonomy Cleanup

This phase should improve reliability and reduce long-tail ambiguity.

1. Tighten tool input contracts
- Expand strict canonical schemas where appropriate.
- Reduce permissive wrapper flattening and string-recovery behavior over time.

2. Clean up taxonomy drift
- Standardize on `rag_pipeline`.
- Remove legacy naming from docs, UI, and API-facing language.

3. Clarify canonical metadata ownership for bound tools
- Explicitly define which fields are runtime mirrors versus owning-domain source of truth.

4. Make category/management metadata first-class
- Distinguish ownership and management from display grouping.

### V4: Hardening

This phase should focus on policy and operational hardening after the model is cleaned up.

1. MCP governance hardening
- Add stronger host allowlist/policy controls.
- Add better operational protections around failures and retries.

2. Expanded regression coverage
- Add API/UI tests around ownership-aware editing surfaces.
- Add function-tool registration/bootstrap tests.
- Add stronger contract tests for strict tool inputs and DTO shape.
