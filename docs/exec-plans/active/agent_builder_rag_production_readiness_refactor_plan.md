# Agent Builder + RAG Pipelines Production-Readiness Refactor Plan

Last Updated: 2026-03-22

## Summary

Refactor the agent builder around a real workflow contract, using the OpenAI Agent Builder model as the reference shape:

- `Start` becomes the authoritative definition of workflow input and global state.
- `input_as_text` becomes a built-in chat workflow input, not editable fake config.
- variable selection becomes inventory-based and typed, not mainly `{{ ... }}`-driven.
- `End` becomes schema-based and produces the authoritative workflow output.
- node outputs become explicit contracts so downstream nodes and `End` can bind to them safely.
- the backend compiler/runtime becomes the source of truth for graph inventory, validation, and output materialization.
- RAG pipelines get the same production-hardening treatment: canonical operator contracts, validation, runtime contract tests, and full scenario coverage.

This should be implemented as a clean-cut graph contract refactor, not a compatibility-heavy patch. The implementation target is a production-ready builder/runtime where long, multi-node, multi-branch, HITL, orchestration, and RAG-backed workflows can be created and executed reliably.

## Implementation Status

Landed in the current refactor pass:
- Graph Spec `3.0` save-path in the builder
- compiler-side graph analysis inventory for `workflow_input`, `state`, and `node_outputs`
- runtime namespace seeding for `workflow_input`, `state`, `state_types`, and canonical `node_outputs`
- schema-based `End` materialization with `ValueRef` bindings
- grouped builder value-picker plumbing backed by live backend graph analysis
- Start/End builder contract editors and classify `input_source` `ValueRef`
- Set State typed assignment metadata, compiler/runtime validation, and builder editor support for `ValueRef` sources
- API-level graph-analysis route coverage and dedicated frontend tests for the Start/End contract editors and graph-analysis hook

Still pending from the full plan:
- broader node-by-node output contract completion and artifact parity
- RAG pipeline contract hardening and parity work
- full API/route analysis coverage and exhaustive scenario/end-to-end tests
- full ConfigPanel integration coverage for the backend-driven analysis loop

## Core Product Decisions

### 1. New agent graph contract version

Introduce Graph Spec `3.0` for the refactored builder/runtime contract.

`3.0` adds:
- compiler-generated workflow input inventory
- typed variable inventory
- explicit node output contracts
- schema-based `End`
- structured value references for data-binding fields

`1.0` and `2.0` remain historical only. The new builder edits and persists `3.0` only.

### 2. Start node semantics

`Start` becomes the workflow contract owner.

For all current builder agents, assume chat workflow semantics:
- the workflow always has built-in `workflow_input.input_as_text: string`
- execution still appends the user input to `messages`
- `input_as_text` is exposed as a first-class runtime variable
- `input_as_text` is read-only and compiler-generated, not user-editable config

`Start` persisted config becomes:
- `state_variables: StateVariableDefinition[]`

`StateVariableDefinition`:
- `key`
- `type`: `string | number | boolean | object | list`
- `default_value` optional

Remove editable `input_variables` from persisted config for chat workflows.

### 3. Runtime variable namespaces

Standardize runtime data into explicit namespaces:

- `workflow_input`
- `state`
- `node_outputs`

Rules:
- `workflow_input` is immutable during a run
- `state` is global mutable workflow state
- `node_outputs` is append-only per node execution result
- prompt/template/CEL resolution must understand all three namespaces consistently

### 4. Node output contracts

Every runtime-producing node must expose a declared output contract. This inventory feeds downstream selectors and `End` bindings.

Initial node output contract defaults:

- `start`
  - workflow input inventory only
- `agent`
  - `output_text: string`
  - `output_json: object | list | unknown` when structured/json output exists
- `llm`
  - `output_text: string`
  - `output_json: object | list | unknown` when structured/json output exists
- `tool`
  - `result: unknown`
- `rag`
  - `results: list`
  - `documents: list`
- `vector_search`
  - `results: list`
  - `documents: list`
- `classify`
  - `category: string`
  - `confidence: number` if available
- `transform`
  - `output: unknown`
- `set_state`
  - no primary node output requirement; writes to `state`
- `human_input`
  - `input_text: string`
- `user_approval`
  - `approved: boolean`
  - `comment: string`
- orchestration/control nodes (`if_else`, `while`, `parallel`, `join`, `router`, `judge`, `replan`, `cancel_subtree`, `spawn_run`, `spawn_group`, `end`)
  - no general downstream output contract unless explicitly added later
- artifact nodes
  - derive output contract from artifact contract metadata

The backend operator registry becomes the authoritative source for node output contracts.

### 5. Structured value references

Add one canonical typed reference model for data-binding fields.

`ValueRef`
- `namespace`: `workflow_input | state | node_output`
- `key`
- `node_id` optional, required for `node_output`
- `expected_type` optional, compiler-populated/validated
- `label` optional, builder-facing only

Use `ValueRef` for fields whose meaning is “pick a value source”, not “write prompt text”.

### 6. End node redesign

Replace current `End` config:
- `output_variable`
- `output_message`

with:
- `output_schema`
- `output_bindings`

`output_schema`
- `name`
- `mode`: `simple | advanced`
- `schema`: JSON Schema

`output_bindings`
- array of `{ json_pointer, value_ref }`

Rules:
- `End` always materializes the final workflow output from schema + bindings
- the final workflow result may be object, array, or primitive in advanced mode
- simple mode supports object schemas only
- advanced mode supports full JSON schema editing
- required schema properties must have bindings
- bindings are variable refs only in v1; no raw literal constants

`End` becomes the authoritative source of `final_output`.

### 7. Text fields vs data-binding fields

Split builder fields into two classes.

Text/prompt fields stay string-based:
- agent instructions
- llm system prompt
- classify instructions
- category descriptions
- human approval message
- user input prompt
- rag/vector query templates
- end-user-facing text templates

These continue to support prompt mentions and variable alias insertion.

Data-binding fields move to `ValueRef`:
- classify input source
- end output bindings
- future fields that semantically mean “pick one variable”

Do not keep using `{{ ... }}` as the primary data model for those fields.

### 8. Set State semantics

`Set State` becomes the canonical way to create/update global workflow variables after `Start`.

Refactor its assignment entries to include type-aware behavior:
- if writing to an existing state key, type must be compatible
- if creating a new state key, the assignment must declare its type
- compiler adds created keys into the downstream state inventory

### 9. Public execution contract

Standardize execution outputs across all execution surfaces.

Execution result should expose:
- `final_output`: authoritative output from `End`
- `messages`: conversation history if present
- optional `assistant_output_text` for chat/thread rendering when relevant

Important hard fix:
- execution APIs must stop treating “last assistant message” as the primary output when `End` exists

## Backend / Runtime Refactor

### 1. Graph schema and compiler

Refactor the graph compiler and schema model to support Spec `3.0`.

Changes:
- add `spec_version: "3.0"`
- remove `Start.input_variables` from persisted chat workflow config
- add `End.output_schema` + `End.output_bindings`
- add `ValueRef` support in graph node config where required
- add graph inventory compilation:
  - workflow input inventory
  - state inventory
  - node output inventory
- validate:
  - duplicate state variable keys
  - invalid keys
  - invalid/missing bindings
  - type mismatches
  - missing required `End` bindings
  - references to unknown node outputs
  - references to outputs not declared by source node type

Canonical backend sources to update:
- `backend/app/agent/graph/schema.py`
- `backend/app/agent/graph/compiler.py`
- `backend/app/agent/executors/standard.py`

### 2. Runtime state and evaluation

Refactor runtime state shape and evaluation semantics.

Changes:
- carry `workflow_input`, `state`, and `node_outputs` explicitly
- `Start` seeds:
  - built-in workflow input values
  - declared state defaults
- `Set State` mutates `state`
- node executions publish declared outputs into `node_outputs`
- CEL/template resolver exposes:
  - `workflow_input`
  - `state`
  - `node_outputs`
  - convenience aliases only if explicitly retained and documented

Do not keep the current ambiguous “sometimes top-level, sometimes nested state” model.

Canonical backend sources to update:
- `backend/app/agent/core/state.py`
- `backend/app/agent/cel_engine.py`
- `backend/app/agent/execution/field_resolver.py`
- `backend/app/agent/graph/node_factory.py`
- `backend/app/agent/execution/service.py`

### 3. Operator metadata hardening

Extend operator specs to declare:
- input field contract type:
  - `text`
  - `template_text`
  - `value_ref`
  - `schema_binding`
- output contract
- field-level type expectations where applicable

The frontend must consume backend metadata instead of carrying parallel truth.

### 4. Builder analysis endpoint

Add a builder-facing graph analysis endpoint, or extend the validation response, to return:
- validation issues
- compiled variable inventory
- compiled node output inventory
- effective node contract metadata

This becomes the canonical source for the builder’s grouped variable pickers and schema binding UI.

### 5. End result materialization

`End` execution must:
- resolve each schema property from its `ValueRef`
- build the final JSON value
- validate the materialized output against the configured schema
- write `final_output`

On validation failure:
- fail the run explicitly
- emit structured trace error with the exact property/pointer

### 6. Observability hardening

Add structured execution trace events for:
- compiled inventory snapshot
- start variable seeding
- set-state writes
- node output publication
- end schema materialization
- end schema validation failure

This is required for debugging production workflows.

## Frontend Builder Refactor

### 1. Start node UI

Refactor `Start` UI to match the product model:

- show `Input variables`
  - read-only built-in `input_as_text`
- show `State variables`
  - typed variable rows
  - per-variable edit modal with:
    - type tabs
    - name
    - default value

Do not allow deleting `input_as_text`.

### 2. Variable inventory picker

Create one shared variable picker used across agent-builder value-binding fields.

Behavior:
- grouped sections:
  - Workflow input
  - State
  - Node outputs grouped by node
- each option shows type badge
- only compatible types are selectable when the field expects a type
- picker source is backend analysis/inventory, not ad hoc frontend flattening

### 3. End node UI

Refactor `End` UI to schema-based output:

- card shows selected output schema chip or “Add schema”
- schema modal has:
  - simple mode
  - advanced mode
- simple mode:
  - schema name
  - property rows
  - property type
  - property value binding via grouped variable picker
- advanced mode:
  - raw JSON schema editor
  - binding view remains structured and pointer-based
- editing simple mode must generate the same canonical stored schema as advanced mode

### 4. Node field refactor

Convert relevant data-binding fields to structured selectors.

Initial required conversion:
- classify input source -> `ValueRef`
- end bindings -> `ValueRef`
- any explicit node input field whose semantics are “choose upstream/global value”

Keep prompt-style inputs text-based for now.

### 5. Shared graph inventory plumbing

Remove the current `availableVariables` flattening-from-Start shortcut in the builder.

Replace it with:
- graph analysis result
- inventory-aware field rendering
- type-aware pickers
- node output discovery

Canonical frontend sources to update:
- `frontend-reshet/src/components/agent-builder/AgentBuilder.tsx`
- `frontend-reshet/src/components/agent-builder/ConfigPanel.tsx`

### 6. RAG pipeline builder hardening

Do not redesign RAG around Start/End, but harden it with the same contract discipline:

- operator registry remains the source of truth
- builder uses canonical operator input/output contracts
- runtime input forms are contract-driven
- terminal output contracts are explicit
- analysis/validation response includes:
  - required runtime inputs
  - terminal outputs
  - data-type compatibility issues

## Implementation Phases

### Phase 1: Contract hard cut
- introduce Graph Spec `3.0`
- add workflow input namespace with built-in `input_as_text`
- add typed state variable definitions
- add `ValueRef`
- add node output contracts
- add graph inventory compilation
- standardize runtime state namespaces

### Phase 2: End schema refactor
- replace `End.output_variable/output_message`
- add schema + bindings model
- implement result materialization and schema validation
- standardize execution APIs to return `final_output`

### Phase 3: Builder refactor
- Start UI redesign
- grouped variable picker
- classify input conversion
- End schema editor and binding flow
- backend-driven inventory usage

### Phase 4: Full hardening + RAG parity
- node output contract completion across all nodes
- artifact node output contract integration
- rag pipeline analysis/contract hardening
- observability and trace coverage
- exhaustive test suite and prod gates

## Exhaustive Test Plan

## A. Test architecture and gating

### 1. Required test layers

Implement all of these:

- backend unit tests
- backend compiler/contract tests
- backend runtime integration tests
- backend API tests
- frontend component tests
- frontend graph serialization tests
- frontend builder interaction tests
- end-to-end workflow execution tests
- end-to-end rag pipeline execution tests
- regression fixture tests
- stress/load tests for long workflows

### 2. Required test roots

- `backend/tests/agent_builder_v3/`
- `backend/tests/rag_pipelines_prod_readiness/`
- `frontend-reshet/src/__tests__/agent_builder_v3/`
- `frontend-reshet/src/__tests__/rag_pipeline_builder_prod/`

Each directory must include `test_state.md`.

### 3. Release gate

The implementation is not done unless:
- all node contract tests pass
- all RAG operator contract tests pass
- all scenario fixtures pass
- all builder serialization roundtrips pass
- all API execution surfaces return the correct `final_output`
- no builder/compiler registry drift remains

## B. Agent builder backend tests

### 1. Graph schema / compiler tests

Cover:

- Graph Spec `3.0` accepted
- pre-`3.0` rejected by new builder path
- exactly one `Start`
- at least one `End`
- unreachable nodes fail
- invalid handles fail
- unknown node types fail
- invalid config shape fails
- invalid `ValueRef` fails
- missing `node_id` on `node_output` ref fails
- unknown state key fails where required
- duplicate state variable names fail
- invalid state variable types fail
- invalid JSON schema on `End` fails
- missing required `End` bindings fail
- schema pointer to nonexistent property fails
- binding type mismatch fails
- artifact node output contract mismatches fail
- orchestration v2 nodes still compile correctly under `3.0`

### 2. Start node tests

Cover:

- `input_as_text` is always present for chat workflows
- `input_as_text` is not persisted as user-editable config
- state defaults are seeded correctly
- default values preserve type
- missing defaults remain unset
- invalid default/type mismatch fails compile
- duplicate state keys fail
- workflow input inventory includes `input_as_text`
- state inventory includes all declared state variables
- start trace events show seeded variables

### 3. Set State tests

Cover:

- write existing state var
- create new state var when explicitly declared by assignment
- reject undeclared creation if the v1 contract requires explicit type
- preserve type on overwrite
- reject incompatible type overwrite
- downstream nodes see updated state
- end bindings read updated values correctly

### 4. Agent / LLM node tests

Cover:

- `output_text` published correctly
- `output_json` published when structured output exists
- prompt fields resolve prompt refs correctly
- variable aliases/templates resolve correctly in prompt text
- empty outputs handled correctly
- runtime model failures surface correct errors
- downstream `End` can bind to `output_text`
- downstream agent can consume prior output as context where supported

### 5. Tool node tests

Cover:
- tool execution publishes `result`
- tool errors are surfaced and traced
- tool output can feed `Transform`, `Set State`, and `End`
- exported tools and manual tools both obey the same node output contract

### 6. RAG / Vector Search node tests inside agent workflows

Cover:
- query template interpolation
- prompt refs in query fields
- fallback behavior when query empty
- `results/documents` published into node output inventory
- downstream agent reads retrieved context correctly
- downstream `End` binds retrieval outputs correctly

### 7. Classify node tests

Cover:
- input binding via `ValueRef`
- category output contract publication
- invalid input binding fails compile
- dynamic handles align to categories
- branch routing works
- category result usable in `If/Else`, `Router`, and `End`

### 8. Transform node tests

Cover:
- transform output publication
- type reshaping works
- invalid expressions fail with structured errors
- transform output can feed `Set State` and `End`

### 9. Control / logic node tests

Cover each node:

- `if_else`
  - true branch
  - false/else branch
  - invalid CEL
- `while`
  - loop executes
  - exit path
  - max-iteration safety
- `parallel`
  - distinct branch success
  - conflicting writes rejected or handled per policy
- `human_input`
  - interrupt before node
  - resume payload accepted
  - output contract publication
- `user_approval`
  - approve path
  - reject path
  - comment propagation
- `join`
  - waits correctly
- `router`
  - handle routing
  - default routing
- `judge`
  - branch decision behavior
- `replan`
  - re-entry/decision behavior
- `cancel_subtree`
  - cancellation propagation
- `spawn_run`
  - child run wiring
- `spawn_group`
  - fanout wiring

### 10. End node tests

Cover:

- simple schema object output
- advanced schema object output
- primitive schema output
- array schema output
- required property binding
- nested object pointer binding
- invalid pointer fails
- materialized output validates successfully
- materialized output validation failure fails run
- `final_output` equals materialized schema result
- multiple end nodes on different branches each work
- output trace includes schema materialization details

### 11. Execution API tests

Cover:
- `execute_agent` returns `final_output`, not last assistant message
- thread/turn persistence still works for chat surfaces
- string final output
- object final output
- array final output
- no assistant message but valid `End` output still returns correctly
- failed `End` schema validation returns structured error

## C. Agent builder frontend tests

### 1. Graph serialization tests

Cover:
- `Start` serialization excludes synthetic `input_as_text`
- `state_variables` serialize cleanly
- `End` schema + bindings serialize cleanly
- simple mode and advanced mode produce the same canonical schema where equivalent
- `ValueRef` serialization roundtrip
- saved graphs rehydrate without drift

### 2. Start UI tests

Cover:
- read-only `input_as_text` always displayed
- cannot delete/edit built-in workflow input
- add state variable
- edit state variable
- change type tabs
- set/remove default
- duplicate state key blocked
- invalid default by type blocked

### 3. Variable picker tests

Cover:
- grouped rendering:
  - Workflow input
  - State
  - Node outputs
- type badges
- type filtering
- search behavior
- node grouping labels
- renaming state variables updates picker
- upstream node output rename updates picker
- stale/invalid refs display safely with validation state

### 4. End UI tests

Cover:
- empty end shows “Add schema”
- selected end shows schema chip
- open simple schema editor
- add/remove property
- bind property to workflow input
- bind property to state
- bind property to node output
- switch to advanced mode
- advanced JSON schema persisted correctly
- invalid advanced schema blocked
- nested property bindings if supported in UI
- required property without binding blocked from save

### 5. Node config UI tests

Cover:
- classify input uses picker, not free text
- prompt text fields still support prompt mentions
- prompt text fields still support variable alias insertion
- end-to-end save/load preserves both prompt mentions and variable refs
- builder consumes backend inventory response, not old Start-only flattening

### 6. Builder interaction tests

Cover:
- create valid multi-node graph from scratch
- save graph
- reload graph
- validate graph
- publish/execute graph
- inspect end result

## D. Full workflow scenario tests

Create golden fixtures for all of these.

### 1. Minimal workflows

- Start -> Agent -> End
- Start -> LLM -> End
- Start -> End

### 2. State-driven workflows

- Start -> Set State -> End
- Start -> Agent -> Set State -> End
- Start -> Transform -> Set State -> End

### 3. Classification flows

- Start -> Classify -> End
- Start -> Classify -> If/Else -> Agent -> End
- Start -> Classify -> Router -> multiple Ends

### 4. Retrieval flows

- Start -> RAG -> Agent -> End
- Start -> Vector Search -> End
- Start -> RAG -> Transform -> End
- Start -> RAG -> Set State -> End

### 5. HITL flows

- Start -> Agent -> User Approval -> Tool -> End
- Start -> Human Input -> Agent -> End
- Start -> Agent -> User Approval reject -> End
- Start -> Human Input pause/resume multi-turn

### 6. Loop and branch flows

- Start -> While -> Agent -> End
- Start -> If/Else -> parallel branches -> Join -> End
- Start -> Parallel -> distinct writers -> Join -> End

### 7. Orchestration flows

- Start -> Spawn Run -> Join -> End
- Start -> Spawn Group -> Join -> End
- Start -> Judge -> Router -> End
- Start -> Replan -> Agent -> End
- Start -> Cancel Subtree branch handling

### 8. Artifact-integrated flows

- Start -> Artifact node -> End
- Start -> Agent -> Artifact node -> End
- artifact node output binding into End schema

### 9. Long workflow production fixtures

At least these large fixtures:

- 15+ node retrieval + classify + approval workflow
- 20+ node multi-branch workflow with state mutations
- orchestration-heavy graph with spawn/join/router/judge/replan
- long workflow ending in structured object output
- long workflow with prompt refs + variable refs + state writes + RAG

Each large fixture must be tested for:
- save/load
- compile
- execute
- traces
- correct final output
- stable behavior across reruns

## E. RAG pipeline production-readiness tests

## 1. Registry / contract tests

For all 22 registered RAG operators:
- operator registered
- category correct
- input type correct
- output type correct
- required config fields correct
- frontend form metadata matches registry
- runtime validator matches registry
- generated inventory snapshot matches live registry

### 2. Builder validation tests

Cover:
- ingestion-only operator filtering
- retrieval-only operator filtering
- invalid cross-mode operator placement rejected
- invalid edge type pairing rejected
- invalid source/sink topology rejected
- missing required source operator rejected
- missing required terminal operator rejected
- invalid knowledge store/model references rejected

### 3. Runtime input contract tests

Cover:
- runtime form generation for every source/input operator
- required field enforcement
- enum enforcement
- number coercion rules
- file input handling
- namespaced payload generation
- payload roundtrip save/load

### 4. Operator category scenario tests

Cover each category:

- source
  - local_loader
  - s3_loader
  - web_crawler
- normalization
  - format_normalizer
  - language_detector
  - pii_redactor
- enrichment
  - classifier
  - entity_recognizer
  - metadata_extractor
  - summarizer
- chunking
  - token_based_chunker
  - recursive_chunker
  - semantic_chunker
  - hierarchical_chunker
- embedding
  - model_embedder
- retrieval
  - query_input
  - vector_search
  - hybrid_search
- reranking
  - model_reranker
  - cross_encoder_reranker
- storage
  - knowledge_store_sink
- output
  - retrieval_result

Every operator needs:
- valid config test
- invalid config test
- happy-path execution test
- error-path execution test
- input/output type contract assertion

### 5. Full ingestion pipeline fixtures

At minimum:
- loader -> normalizer -> chunker -> embedder -> sink
- loader -> enrichment -> chunker -> embedder -> sink
- web crawl -> normalize -> summarize -> chunk -> embed -> sink
- hierarchical chunking ingestion
- file upload ingestion
- ingestion with custom operator in the middle

### 6. Full retrieval pipeline fixtures

At minimum:
- query_input -> vector_search -> retrieval_result
- query_input -> hybrid_search -> retrieval_result
- query_input -> vector_search -> reranker -> retrieval_result
- query_input with filters/top_k params
- retrieval pipeline feeding agent workflow

### 7. RAG + Agent integration tests

Cover:
- agent `rag` node using retrieval pipeline output
- direct vector search node using knowledge store
- store metrics updated after ingestion
- newly ingested content retrievable in agent workflow
- binding retrieved results into `End` output schema

### 8. RAG failure-mode tests

Cover:
- missing store
- invalid credentials
- dimension mismatch
- empty chunk stream
- sink upsert zero results
- model resolution failure
- crawler failure
- file upload missing/expired
- retrieval result operator missing
- retrieval pipeline with no query input
- background execution failure and retry visibility

## F. Cross-system interaction tests

These are required because production readiness depends on surfaces interacting correctly.

### 1. Prompt refs + variable refs

Cover:
- prompt refs in prompt fields with variable alias insertion
- prompt refs in RAG query with workflow input/state values
- prompt rename does not break workflow execution
- variable binding fields and prompt text fields coexist in same graph

### 2. Builder/backend drift tests

Cover:
- operator registry -> frontend config rendering alignment
- output contract metadata -> picker sections alignment
- validation response -> frontend field highlighting alignment
- graph save/load across backend/frontend roundtrip

### 3. Thread/run/event integration

Cover:
- traces include start/end materialization
- pauses/resumes retain workflow input/state/node outputs correctly
- run output_result stores final structured output
- thread surfaces remain valid for chat-oriented agents

### 4. Publish/versioning tests

Cover:
- draft save
- publish
- version snapshot
- execute published version
- inventory stability across versions
- schema change between versions does not corrupt older runs

## G. Stress, load, and soak tests

### 1. Large graph compile tests

- 25-node graph compile
- 40-edge graph compile
- many state variables
- many end bindings
- compile latency budget assertions

### 2. Runtime soak tests

- repeated execution of large graphs
- repeated execution of retrieval-heavy graphs
- repeated HITL resume cycles
- repeated orchestration fanout/join cycles

### 3. Concurrency tests

- parallel runs of same graph
- parallel runs of same RAG pipeline
- concurrent writes to same knowledge store
- concurrent agent runs sharing prompt refs/state definitions safely

### 4. Failure recovery tests

- one branch fails in parallel workflow
- rerun after partial failure
- resumed run after pause
- execution service restart recovery if already supported by current infrastructure

## H. Production-readiness acceptance criteria

The refactor is considered done only when all of these are true:

- Start is real, typed, and authoritative
- `input_as_text` exists and works across builder, compiler, runtime, and picker
- variable inventory is backend-canonical and grouped correctly
- End is schema-based and authoritative
- execution APIs return `final_output` correctly for string and structured outputs
- all registered agent node types have contract tests
- all registered RAG operators have contract tests
- all large fixture workflows and pipelines pass
- builder save/load/execute cycles are stable
- trace/debug surfaces expose enough detail to debug field binding failures
- no known builder/runtime drift remains between metadata, validation, and execution

## Assumptions and defaults

- This is a clean-cut refactor centered on Graph Spec `3.0`.
- No legacy compatibility path is required inside the new builder/runtime implementation.
- All current builder agents are treated as chat workflows for Start-node semantics.
- `input_as_text` is compiler/runtime-generated, not persisted user config.
- `End` is schema-backed in the new contract; old `output_variable/output_message` is removed.
- Text/prompt fields remain string-based; data-binding fields move to structured refs.
- RAG pipelines keep their current domain model, but receive contract hardening and exhaustive test coverage rather than a Start/End redesign.
