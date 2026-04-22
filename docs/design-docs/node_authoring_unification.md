# Node Authoring Unification

Last Updated: 2026-04-22

## Purpose

Define the canonical authoring surface shared by agent graphs and RAG pipelines while keeping execution/runtime layers separate.

## Core Decision

All builder and discovery surfaces should consume one canonical backend model:

- `NodeAuthoringSpec`
- `NodeCatalogItem`

This layer is for authoring only. It is not the runtime contract.

## Backend-Owned Authoring Pipeline

The canonical spec is now only the first layer.

Authoring flows should pass through a shared backend pipeline:

1. `NodeAuthoringSpec` discovery
2. backend normalization
3. repair-grade authoring validation
4. existing compiler/runtime

Normalization is authoritative on the backend and runs inside existing create, update, patch, and compile-entry flows.

There is no standalone normalize-preview endpoint.

Frontend builders may still prefill from schema defaults for UX, but that remains a mirror of backend schema defaults, not a second default source.

## Canonical Authoring Spec

`NodeAuthoringSpec` is the single schema returned to builders and discovery tools.

Fields:

- `type`
- `title`
- `description`
- `category`
- `input_type`
- `output_type`
- `config_schema`
- `output_schema`
- `field_contracts`
- `graph_hints`

## Graph Hints

`graph_hints` stays intentionally small.

- `editor`: `generic | start | end | classify | set_state`
- `branching`: minimal metadata for non-default output handles

No runtime logic, compiler rules, or persistence details belong here.

## Config Schema

`config_schema` is canonical and schema-first.

- JSON Schema carries field types, defaults, descriptions, enums, and required fields
- UI-only metadata lives in `x-ui`
- supported `x-ui` keys are lean and declarative

Current supported keys:

- `widget`
- `visibility`
- `group`
- `order`
- `rows`
- `dependsOn`
- `helpKind`
- `promptCapable`
- `promptSurface`
- `artifactInputs`
- `placeholder`

There is no separate canonical `configFields`, `defaults`, `required_config`, or `optional_config` payload.

Simple defaults live in `config_schema.properties[*].default`.

Computed or shape-level defaults belong in backend normalizers, not in the frontend.

## Output Schema

`output_schema` is canonical for:

- downstream value-reference discovery
- graph analysis
- architect/discovery tooling

Display summaries should be derived from `output_schema`, not stored as a second contract.

## Catalog Surface

`NodeCatalogItem` is the compact palette/discovery view.

Fields:

- `type`
- `title`
- `description`
- `category`
- `input_type`
- `output_type`
- `required_config_fields`
- `icon`
- `color`
- `editor`

## Domain Boundaries

Shared:

- authoring metadata
- discovery payload shape
- schema-driven builder rendering

Not shared:

- graph persistence shapes
- runtime registries
- compiler logic
- execution semantics
- topology rules

## Domain Mapping

### Agent Graphs

Built-in agent operators and artifact-backed nodes are projected into `NodeAuthoringSpec`.

Agent discovery endpoints:

- `GET /agents/nodes/catalog`
- `POST /agents/nodes/schema`

`POST /agents/nodes/schema` returns:

- `specs`
- `unknown`
- `instance_contract`

### RAG Pipelines

Retrieval and ingestion operators are projected into the same authoring model.

RAG discovery endpoints return the same canonical shapes:

- flat catalog items
- `specs`
- one top-level `instance_contract`

Retrieval and ingestion remain separate pipeline families at the runtime layer.

## Builder Rules

Builders should:

- fetch compact catalog items first
- lazy-load schemas per selected type
- render config from `config_schema`
- use schema defaults only as an immediate UX mirror
- use only the minimal special editors declared in `graph_hints.editor`
- treat backend-normalized saved graphs as canonical

Builders should not:

- carry their own canonical node spec tables
- rebuild field contracts from legacy payloads
- depend on backend-specific `ui.configFields` or raw RAG `required_config` / `optional_config`
- invent extra defaults the backend does not own

## Authoring Validation

Authoring validation should return stable repair-oriented issues with:

- `code`
- `message`
- `severity`
- `path`
- `node_id`
- `edge_id`
- `expected`
- `actual`
- `suggestions`
- optional `suggested_value`
- optional `repair_hint`

Compiler/runtime validation remains in place, but authoring surfaces should adapt those errors into this stable authoring contract.

## Design Goal

The system should make adding a new node/operator require:

1. runtime registration in its own domain
2. one canonical authoring projection

No second frontend spec definition should be required.
