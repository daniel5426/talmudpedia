# Agent Node Authoring Current

Last Updated: 2026-04-22

## Purpose

Describe the current canonical authoring model for agent nodes.

This document is about authoring and discovery, not execution internals.

Use it when working on:

- agent builder node settings
- node discovery endpoints
- platform-architect graph authoring
- future custom node authoring contracts

## Canonical Authoring Surface

Agent node authoring is now centered on the shared backend authoring layer:

- `NodeCatalogItem`
- `NodeAuthoringSpec`
- backend normalization
- repair-grade authoring validation

The runtime registry and executors remain separate. The authoring layer is a projection of runtime node definitions for builders and model-facing tooling.

## Discovery Endpoints

Canonical agent-node discovery endpoints:

- `GET /agents/nodes/catalog`
- `POST /agents/nodes/schema`

`GET /agents/nodes/catalog` returns the compact palette/discovery surface.

`POST /agents/nodes/schema` returns:

- `specs`
- `instance_contract`

The old `/agents/operators` surface is no longer the canonical builder/discovery contract.

## Authoring Contract

Each node type is exposed as a `NodeAuthoringSpec` with:

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

Important rules:

- `config_schema` is canonical
- builder UI fields are derived from schema plus `x-ui`
- backend defaults are authoritative
- persisted graph config is backend-normalized before write

## Builder Rules

The builder should:

- fetch catalog first
- fetch node schema for the selected type
- render settings from `config_schema`
- use backend schema defaults for immediate UX only
- treat backend-normalized saved graphs as canonical

The builder should not:

- own a second canonical node spec table
- keep local default tables that disagree with backend schema
- depend on legacy `ui.configFields` as the canonical contract

## Current Supported End-User Node Surface

Current registered built-in agent nodes:

### Control

- `start`
- `end`

### Reasoning

- `agent`
- `classify`

### Data

- `transform`
- `set_state`
- `speech_to_text`

### Logic

- `if_else`
- `while`
- `parallel`

### Action

- `tool`
- `rag`
- `vector_search`

### Interaction

- `user_approval`

## Hidden Runtime Nodes

The orchestration family still exists at the runtime/graph level:

- `spawn_run`
- `spawn_group`
- `join`
- `router`
- `judge`
- `replan`
- `cancel_subtree`

These are intentionally hidden from the public end-user node catalog but still supported by runtime, graph loading, and generated/internal authoring flows.

## Removed Legacy Nodes

These legacy nodes are removed from the standard authoring surface:

- `human_input`
- `conditional`

They should not appear in:

- builder catalogs
- builder settings contracts
- canonical authoring docs
- new graphs authored by platform tools

## Current Special Editors

Only a small set of explicit special editors remain:

- `start`
- `end`
- `classify`
- `set_state`

Everything else should prefer generic schema-driven config rendering unless a strong UX reason justifies a narrow exception.

## Backend-Owned Normalization

Agent graph writes normalize before persistence.

Current normalization responsibilities include:

- schema default application
- stable branch-id generation for `classify` and `if_else`
- route-table normalization for `router` and `judge`
- canonical `end` output config shaping
- typed `set_state` assignment normalization
- stripping removed per-node config noise such as deprecated `name` fields on nodes where `name` is no longer part of the authoring contract

This is critical for platform-architect graph generation because the model should not have to author mechanical boilerplate perfectly.

## Current Node Polish Rules

For end-user node settings, prefer:

- required fields only when semantically necessary
- removal of meaningless per-node config such as decorative `name` fields
- schema-first contracts for all node settings
- declarative branching metadata instead of frontend assumptions

Recent contract cleanup already applied:

- `if_else` is schema-first
- `while` is schema-first
- `transform` is schema-first
- `user_approval` is schema-first
- useless per-node `name` config was removed from `classify`, `transform`, `set_state`, `while`, and `user_approval`

## Relation To Platform Architect

This node authoring layer is now strong enough to support the agreed architect direction:

- discovery first
- canonical graph authoring
- backend-owned defaults and normalization
- repair-friendly validation

The remaining architect work should build on this surface instead of inventing a parallel node-description path.
